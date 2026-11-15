"""Boundary-contained samples of illustrative wind-turbine power potential.

Boundaries: NDMC SouthAfricaBoundaries public service, credited to MDB.
Weather: Open-Meteo 100 m hourly numerical weather output.
No interpolation, installed turbines, electricity flows or municipal totals.
"""
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import math
import time

import numpy as np
import requests
from pyproj import Transformer
from shapely.geometry import Point, mapping, shape
from shapely.ops import transform

from wind_data import coordinates, power_curve

BOUNDARIES = 'https://gislive21.ndmc.gov.za/hosting/rest/services/SouthAfricaBoundaries/MapServer'
LAYERS = {'municipality': 2, 'province': 0}
FORWARD = Transformer.from_crs(4326, 6933, always_xy=True).transform
INVERSE = Transformer.from_crs(6933, 4326, always_xy=True).transform


def request_json(url, params):
    response = requests.get(url, params=params, timeout=40,
                            headers={'User-Agent': 'WindScope/1.0 (local non-commercial research)'})
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict) and data.get('error'):
        raise ValueError('Spatial or weather provider could not fulfil this request.')
    return data


@lru_cache(maxsize=80)
def boundary(lat, lon, level, day):
    data = request_json(f'{BOUNDARIES}/{LAYERS[level]}/query', {
        'f': 'geojson', 'geometry': f'{lon},{lat}', 'geometryType': 'esriGeometryPoint',
        'inSR': 4326, 'spatialRel': 'esriSpatialRelIntersects', 'outFields': '*',
        'returnGeometry': 'true', 'outSR': 4326, 'maxAllowableOffset': .001, 'geometryPrecision': 5})
    features = data.get('features', [])
    if not features:
        raise ValueError('No South African boundary found for this point at the selected level. Offshore points may be outside municipal boundaries.')
    if len(features) != 1:
        raise ValueError('This point intersects multiple boundaries. Select a point clearly inside one area.')
    feature = features[0]
    props = feature['properties']
    geom = shape(feature['geometry'])
    if geom.is_empty or not geom.is_valid:
        raise ValueError('The boundary provider returned invalid geometry. Try another area.')
    name = props.get('MUNICNAME') if level == 'municipality' else props.get('PROVINCE')
    code = props.get('MUN_CD') if level == 'municipality' else props.get('CODE')
    return {'type': 'Feature', 'geometry': mapping(geom),
            'properties': {'name': str(name or 'Unnamed area').strip(), 'code': str(code or '').strip(),
                           'level': level, 'boundary_source': BOUNDARIES,
                           'boundary_credit': 'Municipal Demarcation Board / NDMC public GIS service',
                           'boundary_vintage': 'Not specified in service metadata; not verified as 2026 demarcations',
                           'boundary_retrieved_day': day,
                           'display_simplification_degrees': .001}}


def sample_area(geojson, size=5):
    """Equal-area grid centres clipped to the served polygon, including holes."""
    geom = transform(FORWARD, shape(geojson))
    xmin, ymin, xmax, ymax = geom.bounds
    dx, dy = (xmax-xmin)/size, (ymax-ymin)/size
    samples = []
    for row in range(size):
        for col in range(size):
            p = Point(xmin+(col+.5)*dx, ymin+(row+.5)*dy)
            if geom.covers(p):
                lon, lat = INVERSE(p.x, p.y)
                samples.append({'lat': round(lat, 6), 'lon': round(lon, 6)})
    if not samples:
        p = geom.representative_point()
        lon, lat = INVERSE(p.x, p.y)
        samples = [{'lat': lat, 'lon': lon}]
    return samples, {'sampling': '5 × 5 equal-area grid centres, clipped to simplified served boundary',
                     'spacing_x_km': round(dx/1000, 2), 'spacing_y_km': round(dy/1000, 2),
                     'boundary_area_km2': round(geom.area/1e6, 1)}


@lru_cache(maxsize=48)
def batch_weather(points, bucket):
    data = request_json('https://api.open-meteo.com/v1/forecast', {
        'latitude': ','.join(str(p[0]) for p in points),
        'longitude': ','.join(str(p[1]) for p in points),
        'hourly': 'wind_speed_100m,wind_direction_100m',
        'wind_speed_unit': 'ms', 'timezone': 'GMT', 'forecast_days': 3})
    return (data if isinstance(data, list) else [data]), datetime.now(timezone.utc).isoformat()


def distribution(lat, lon, level='municipality', rated_kw=2000, ahead=0):
    lat, lon = coordinates(lat, lon)
    if level not in LAYERS or ahead not in (0, 6, 12, 24) or not math.isfinite(rated_kw) or not 1 <= rated_kw <= 20000:
        raise ValueError('Select municipality/province, a valid capacity and 0/6/12/24 hours ahead.')
    feature = boundary(round(lat, 5), round(lon, 5), level, datetime.now(timezone.utc).date().isoformat())
    points, sampling = sample_area(feature['geometry'])
    weather, fetched_at = batch_weather(tuple((p['lat'], p['lon']) for p in points), int(time.time()//600))
    if len(weather) != len(points):
        raise ValueError('Weather provider returned an incomplete set of locations.')
    target = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)+timedelta(hours=ahead)
    target_string = target.strftime('%Y-%m-%dT%H:%M')
    results = []
    for i, (point, data) in enumerate(zip(points, weather)):
        h = data.get('hourly', {})
        try:
            index = h['time'].index(target_string)
            speed = h['wind_speed_100m'][index]
            if speed is None or not math.isfinite(speed) or speed < 0:
                continue
            kw = float(power_curve(speed, rated_kw))
            results.append({**point, 'sample_id': i+1, 'speed': speed,
                            'direction': h['wind_direction_100m'][index], 'power_kw': round(kw, 2),
                            'capacity_percent': round(kw/rated_kw*100, 1),
                            'grid_lat': data['latitude'], 'grid_lon': data['longitude']})
        except (KeyError, ValueError, IndexError, TypeError):
            continue
    if not results:
        raise ValueError('No modelled wind is available for the common map timestamp.')
    values = [p['power_kw'] for p in results]
    return {'boundary': feature, 'samples': results, **sampling, 'requested_samples': len(points),
            'missing_samples': len(points)-len(results), 'valid_time': target.isoformat(), 'ahead_hours': ahead,
            'fetched_at': fetched_at, 'rated_kw': rated_kw,
            'unique_weather_grid_points': len({(p['grid_lat'],p['grid_lon']) for p in results}),
            'summary': {'sample_mean_kw': round(float(np.mean(values)), 1), 'sample_min_kw': min(values),
                        'sample_max_kw': max(values)},
            'source': 'Open-Meteo numerical weather at 100 m, illustrative single-turbine power curve',
            'limitations': 'Point samples, not a continuous surface or installed generation. Sample values must not be added into municipal/provincial totals. Coarse weather grids can repeat across samples. No siting constraints, losses, grid connection or neural spatial model.'}
