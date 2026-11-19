"""ERA5 native 0.25 degree grid display via Open-Meteo, with no interpolation."""
from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from shapely.geometry import box, mapping, shape
from shapely.ops import transform

from spatial_power import boundary, FORWARD, request_json
from wind_data import coordinates, power_curve

RESOLUTION = .25
MAX_CELLS = 1200


def period(start, end, hour=None):
    try:
        start, end = date.fromisoformat(start), date.fromisoformat(end)
    except (TypeError, ValueError):
        raise ValueError('Choose valid ISO start and end dates.')
    latest = datetime.now(timezone.utc).date()-timedelta(days=7)
    if start < date(1940,1,1) or end < start or end > latest:
        raise ValueError(f'ERA5 dates must be from 1940-01-01 through {latest}; end must follow start. A seven-day archive buffer is used.')
    if (end-start).days >= 366:
        raise ValueError('Choose a period of at most 366 days per layer.')
    if hour is not None and (type(hour) is not int or not 0 <= hour <= 23 or start != end):
        raise ValueError('A selected hour requires one date and an hour from 0 to 23 UTC.')
    return start, end


def grid_cells(geometry):
    """All ERA5-centred display footprints intersecting the served boundary."""
    area = shape(geometry)
    xmin,ymin,xmax,ymax = area.bounds
    cells=[]
    for iy in range(math.floor((ymin-.125)/RESOLUTION), math.ceil((ymax+.125)/RESOLUTION)+1):
        lat=round(iy*RESOLUTION, 6)
        for ix in range(math.floor((xmin-.125)/RESOLUTION), math.ceil((xmax+.125)/RESOLUTION)+1):
            lon=round(ix*RESOLUTION, 6)
            clipped=area.intersection(box(lon-.125,lat-.125,lon+.125,lat+.125))
            if clipped.is_empty or clipped.geom_type not in ('Polygon','MultiPolygon'):
                continue
            km2=transform(FORWARD,clipped).area/1e6
            if km2 < .0001:
                continue
            cells.append({'lat':lat,'lon':lon,'geometry':mapping(clipped),'clipped_area_km2':km2})
    if not cells or len(cells)>MAX_CELLS:
        raise ValueError(f'Area contains {len(cells)} ERA5 display cells; supported range is 1–{MAX_CELLS}.')
    return cells


def aggregate(data, lat, lon, start, end, rated_kw, hour=None):
    # Nearest selection and disabled elevation adjustment preserve grid identity.
    if abs(float(data.get('latitude',999))-lat)>.001 or abs(float(data.get('longitude',999))-lon)>.001:
        raise ValueError('Archive returned a different grid coordinate; refusing to label it as this ERA5 cell.')
    h=data.get('hourly',{})
    stamps=h.get('time',[])
    speeds=h.get('wind_speed_100m',[])
    expected=(end-start).days*24+24
    wanted=[(datetime.combine(start,datetime.min.time())+timedelta(hours=i)).strftime('%Y-%m-%dT%H:%M') for i in range(expected)]
    if len(stamps)!=expected or stamps!=wanted or len(speeds)!=expected:
        raise ValueError('ERA5 response has missing, duplicate or unexpected hours.')
    values=np.asarray([np.nan if v is None else v for v in speeds],dtype=float)
    if hour is not None:
        values=values[hour:hour+1]
    if not np.isfinite(values).all() or (values<0).any():
        return None
    hourly_power=power_curve(values,rated_kw)
    return {'wind_speed_mps':float(np.mean(values)), 'power_kw':float(np.mean(hourly_power)),
            'energy_mwh':float(np.sum(hourly_power)/1000), 'hours':len(values),
            'capacity_percent':float(np.mean(hourly_power)/rated_kw*100)}


def layer(lat,lon,level,start,end,rated_kw,cache_dir,hour=None,progress=lambda **kw:None):
    lat,lon=coordinates(lat,lon)
    first,last=period(start,end,hour)
    if level not in ('municipality','province') or not math.isfinite(rated_kw) or not 1 <= rated_kw <= 20000:
        raise ValueError('Choose municipality/province and a valid turbine capacity.')
    progress(stage='Identifying administrative boundary',completed=0,total=0)
    feature=boundary(round(lat,5),round(lon,5),level,datetime.now(timezone.utc).date().isoformat())
    cells=grid_cells(feature['geometry'])
    progress(stage='Downloading hourly ERA5 grid data',completed=0,total=len(cells))
    cache_dir=Path(cache_dir)
    cache_dir.mkdir(parents=True,exist_ok=True)
    output=[]
    missing=0
    retrieved=[]
    for offset in range(0,len(cells),16):
        batch=cells[offset:offset+16]
        pending=[]
        responses={}
        for c in batch:
            key=hashlib.sha256(f"era5-nearest-unadjusted-v1/{c['lat']}/{c['lon']}/{start}/{end}".encode()).hexdigest()
            cache_file=cache_dir/(key+'.json.gz')
            if cache_file.exists():
                try:
                    with gzip.open(cache_file,'rt',encoding='utf8') as f:
                        responses[(c['lat'],c['lon'])]=json.load(f)
                    continue
                except (OSError,ValueError):
                    pass
            pending.append((c,cache_file))
        if pending:
            data=request_json('https://archive-api.open-meteo.com/v1/archive',{
                'latitude':','.join(str(c['lat']) for c,_ in pending),
                'longitude':','.join(str(c['lon']) for c,_ in pending),
                'start_date':start,'end_date':end,'hourly':'wind_speed_100m',
                'models':'era5','wind_speed_unit':'ms','timezone':'GMT',
                'cell_selection':'nearest','elevation':','.join('nan' for _ in pending)})
            rows=data if isinstance(data,list) else [data]
            if len(rows)!=len(pending):
                raise ValueError('Archive returned an incomplete set of ERA5 cells.')
            for (c,file),d in zip(pending,rows):
                d['_retrieved_at']=datetime.now(timezone.utc).isoformat()
                # Validate coordinate and timestamps before persisting this response.
                aggregate(d,c['lat'],c['lon'],first,last,rated_kw,hour)
                with gzip.open(file,'wt',encoding='utf8') as f:
                    json.dump(d,f)
                responses[(c['lat'],c['lon'])]=d
        for c in batch:
            d=responses[(c['lat'],c['lon'])]
            stats=aggregate(d,c['lat'],c['lon'],first,last,rated_kw,hour)
            retrieved.append(d['_retrieved_at'])
            if stats is None:
                missing+=1
                continue
            output.append({'type':'Feature','geometry':c['geometry'],'properties':{
                **stats,'cell_id':len(output)+1,'lat':c['lat'],'lon':c['lon'],
                'clipped_area_km2':c['clipped_area_km2'],'grid_degrees':RESOLUTION,
                'wind_height_m':100,'wind_unit':'m/s','power_unit':'kW',
                'power_type':'Illustrative per-turbine estimate, hourly power averaged over period'}})
        progress(stage='Aggregating hourly wind and power',completed=min(offset+len(batch),len(cells)),total=len(cells))
    if not output:
        raise ValueError('No complete ERA5 cells are available for this period.')
    weights=np.array([f['properties']['clipped_area_km2'] for f in output])
    full_area=sum(c['clipped_area_km2'] for c in cells)
    def stats(key):
        values=np.array([f['properties'][key] for f in output])
        return {'area_weighted_mean':float(np.average(values,weights=weights)),'min':float(values.min()),'max':float(values.max())}
    return {'source':'ERA5 via Open-Meteo Historical Weather API; ECMWF/Copernicus',
            'boundary':feature,'cells':{'type':'FeatureCollection','features':output},
            'start_date':start,'end_date':end,'hour_utc':hour,'hours_per_cell':output[0]['properties']['hours'],
            'rated_kw':rated_kw,'grid_degrees':RESOLUTION,'requested_cells':len(cells),'missing_cells':missing,
            'coverage_percent':float(weights.sum()/full_area*100),'retrieved_first':min(retrieved),'retrieved_last':max(retrieved),
            'summary':{'wind_speed_mps':stats('wind_speed_mps'),'power_kw':stats('power_kw')},
            'method':'ERA5 0.25° grid-centred display footprints clipped to served boundary; no spatial interpolation. Hourly 100 m wind; nearest grid selection; elevation adjustment disabled. Power curve applied hourly before averaging. Area-weighted summary uses clipped EPSG:6933 cell areas.',
            'limitations':'Reanalysis grid (~25 km), not local measurements or a turbine siting assessment. Display footprints approximate grid support; no new detail is created at municipal borders. Missing-hour cells are excluded. Illustrative per-turbine power, not installed generation or municipal totals. Boundary vintage unspecified.'}
