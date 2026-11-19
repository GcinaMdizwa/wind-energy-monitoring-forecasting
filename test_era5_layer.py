from datetime import date, datetime, timedelta
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from shapely.geometry import Polygon, box, mapping, shape
from shapely.ops import unary_union

from era5_layer import aggregate, grid_cells, layer, period
from wind_data import power_curve


def response(lat,lon,values):
    return {'latitude':lat,'longitude':lon,'hourly':{
        'time':[(datetime(2025,1,1)+timedelta(hours=i)).strftime('%Y-%m-%dT%H:%M') for i in range(len(values))],
        'wind_speed_100m':values}}


class ERA5Tests(unittest.TestCase):
    def test_clipped_cells_cover_area_and_preserve_holes(self):
        geom=Polygon([(24,-34),(25,-34),(25,-33),(24,-33)],
                     [[(24.2,-33.8),(24.8,-33.8),(24.8,-33.2),(24.2,-33.2)]])
        cells=grid_cells(mapping(geom))
        union=unary_union([shape(c['geometry']) for c in cells])
        self.assertAlmostEqual(union.symmetric_difference(geom).area,0,places=9)
        for c in cells:
            self.assertAlmostEqual(c['lat']/.25,round(c['lat']/.25))
            self.assertLess(shape(c['geometry']).difference(geom).area,1e-10)

    def test_power_is_hourly_then_averaged(self):
        values=[3,12]*12
        stats=aggregate(response(-34,25,values),-34,25,date(2025,1,1),date(2025,1,1),2000)
        self.assertEqual(stats['power_kw'],1000)
        self.assertNotAlmostEqual(stats['power_kw'],float(power_curve(np.mean(values))))
        self.assertEqual(stats['energy_mwh'],24)
        self.assertEqual(stats['hours'],24)

    def test_hour_and_missing_data(self):
        values=[None]+[12]*23
        self.assertIsNone(aggregate(response(-34,25,values),-34,25,date(2025,1,1),date(2025,1,1),2000))
        stats=aggregate(response(-34,25,values),-34,25,date(2025,1,1),date(2025,1,1),2000,1)
        self.assertEqual(stats['hours'],1)
        self.assertEqual(stats['power_kw'],2000)
        d=response(-34,25,[12]*24);d['hourly']['time'][1]=d['hourly']['time'][0]
        with self.assertRaises(ValueError):aggregate(d,-34,25,date(2025,1,1),date(2025,1,1),2000)

    def test_grid_coordinate_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            aggregate(response(-33.9,25,[12]*24),-34,25,date(2025,1,1),date(2025,1,1),2000)

    def test_date_limits_and_leap_year(self):
        self.assertEqual((period('2024-01-01','2024-12-31')[1]-date(2024,1,1)).days,365)
        for a,b,h in [('2025-01-01','2026-01-02',None),('2099-01-01','2099-01-01',None),('2025-01-01','2025-01-02',1),('2025-01-01','2025-01-01',24)]:
            with self.assertRaises(ValueError):period(a,b,h)

    def test_explicit_era5_parameters_and_local_cache(self):
        feature={'type':'Feature','geometry':mapping(box(24.9,-34.1,25.1,-33.9)),
                 'properties':{'name':'Test municipality','level':'municipality'}}
        def provider(url,params):
            self.assertEqual(params['models'],'era5');self.assertEqual(params['cell_selection'],'nearest')
            self.assertTrue(all(e=='nan' for e in params['elevation'].split(',')))
            return [response(float(lat),float(lon),[12]*24) for lat,lon in zip(params['latitude'].split(','),params['longitude'].split(','))]
        with tempfile.TemporaryDirectory() as folder,patch('era5_layer.boundary',return_value=feature),patch('era5_layer.request_json',side_effect=provider) as req:
            result=layer(-34,25,'municipality','2025-01-01','2025-01-01',2000,folder)
            self.assertEqual(result['summary']['power_kw']['area_weighted_mean'],2000)
            self.assertEqual(result['coverage_percent'],100)
            n=req.call_count
            layer(-34,25,'municipality','2025-01-01','2025-01-01',3000,folder)
            self.assertEqual(req.call_count,n)


if __name__=='__main__':unittest.main()
