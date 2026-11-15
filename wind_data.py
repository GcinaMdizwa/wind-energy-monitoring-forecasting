"""Public weather adapters. Weather models are not turbine telemetry."""
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import json
import math
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


def get_json(base, params):
    req = Request(base + '?' + urlencode(params), headers={'User-Agent': 'WindScope-research-dashboard/1.0'})
    with urlopen(req, timeout=35) as response:
        return json.load(response)


def coordinates(lat, lon):
    lat, lon = float(lat), float(lon)
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError('Enter valid latitude (-90 to 90) and longitude (-180 to 180).')
    return lat, lon


def search(query):
    if len(query.strip()) < 2:
        return []
    data = get_json('https://geocoding-api.open-meteo.com/v1/search',
                    {'name': query[:120], 'count': 8, 'language': 'en', 'format': 'json'})
    return [{'name': r['name'], 'label': ', '.join(filter(None, [r['name'], r.get('admin1'), r.get('country')])),
             'lat': r['latitude'], 'lon': r['longitude']} for r in data.get('results', [])]


def power_curve(speed, rated_kw=2000):
    """Illustrative cubic curve: cut-in 3, rated 12, cut-out 25 m/s."""
    v = np.asarray(speed, dtype=float)
    result = float(rated_kw) * np.clip((v**3 - 3**3) / (12**3 - 3**3), 0, 1)
    result = np.where((v < 3) | (v >= 25), 0, result)
    return result


@lru_cache(maxsize=48)
def _weather(lat, lon, bucket):
    data = get_json('https://api.open-meteo.com/v1/forecast', {
        'latitude': lat, 'longitude': lon, 'current': 'wind_speed_10m,wind_direction_10m,temperature_2m',
        'hourly': 'wind_speed_100m,wind_direction_100m,temperature_2m',
        'wind_speed_unit': 'ms', 'timezone': 'GMT', 'past_days': 2, 'forecast_days': 3})
    data['_retrieved_at'] = datetime.now(timezone.utc).isoformat()
    return data


def monitor(lat, lon, rated_kw=2000):
    lat, lon = coordinates(lat, lon)
    data = _weather(lat, lon, int(time.time() // 600))
    h = data['hourly']
    now = datetime.now(timezone.utc)
    rows = []
    for i, stamp in enumerate(h['time']):
        speed = h['wind_speed_100m'][i]
        if speed is None:
            continue
        dt = datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
        rows.append({'time': dt.isoformat(), 'speed': speed,
                     'direction': h['wind_direction_100m'][i],
                     'power_kw': round(float(power_curve(speed, rated_kw)), 2), 'future': dt > now})
    current = data.get('current', {})
    return {'rows': rows, 'current': current, 'fetched_at': data['_retrieved_at'],
            'grid_lat': data['latitude'], 'grid_lon': data['longitude'],
            'source': 'Open-Meteo numerical weather model', 'height_m': 100,
            'power_source': 'Illustrative turbine curve; not measured generation', 'rated_kw': rated_kw}


def history(lat, lon, years=1):
    lat, lon = coordinates(lat, lon)
    if years not in (1, 2, 3, 5):
        raise ValueError('Choose 1, 2, 3 or 5 years of history.')
    end = date.today() - timedelta(days=7)
    start = end - timedelta(days=365 * years)
    data = get_json('https://archive-api.open-meteo.com/v1/archive', {
        'latitude': lat, 'longitude': lon, 'start_date': start.isoformat(), 'end_date': end.isoformat(),
        'hourly': 'wind_speed_100m,wind_direction_100m', 'models': 'era5',
        'wind_speed_unit': 'ms', 'timezone': 'GMT'})
    h = data['hourly']
    frame = pd.DataFrame({'timestamp': pd.to_datetime(h['time'], utc=True),
                          'wind_speed_mps': h['wind_speed_100m'],
                          'wind_direction_deg': h['wind_direction_100m']})
    if frame.isna().any().any():
        raise ValueError('Archive contains missing hours. Resolve gaps before model training.')
    return frame, {'source': 'Open-Meteo / ERA5 reanalysis at 100 m', 'start': start.isoformat(),
                   'end': end.isoformat(), 'lat': lat, 'lon': lon, 'years': years,
                   'target': 'wind speed (m/s); power subsequently estimated with illustrative curve'}
