import unittest
from unittest.mock import patch

from shapely.geometry import Point, Polygon, MultiPolygon, mapping, shape
from spatial_power import sample_area, distribution


class SpatialTests(unittest.TestCase):
    def test_grid_respects_holes(self):
        area=Polygon([(20,-34),(21,-34),(21,-33),(20,-33)],
                     [[(20.3,-33.7),(20.7,-33.7),(20.7,-33.3),(20.3,-33.3)]])
        points, info=sample_area(mapping(area))
        self.assertGreater(len(points),0)
        self.assertLessEqual(len(points),25)
        self.assertTrue(all(area.covers(Point(p['lon'],p['lat'])) for p in points))
        self.assertGreater(info['spacing_x_km'],0)

    def test_narrow_multipart_area_uses_inside_fallback(self):
        area=MultiPolygon([Polygon([(20,-34),(20.001,-34),(20.001,-33.99),(20,-33.99)]),
                           Polygon([(21,-33),(21.001,-33),(21.001,-32.99),(21,-32.99)])])
        points,_=sample_area(mapping(area))
        self.assertTrue(all(area.covers(Point(p['lon'],p['lat'])) for p in points))

    def test_identical_timestamp_and_no_municipal_total(self):
        from datetime import datetime, timezone
        time=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:00')
        feature={'type':'Feature','geometry':mapping(Polygon([(20,-34),(21,-34),(21,-33),(20,-33)])),
                 'properties':{'name':'Test boundary','level':'municipality'}}
        weather={'latitude':-33.5,'longitude':20.5,'hourly':{'time':[time],
                 'wind_speed_100m':[12.0],'wind_direction_100m':[180]}}
        with patch('spatial_power.boundary',return_value=feature), patch('spatial_power.batch_weather') as batch:
            batch.side_effect=lambda points,bucket:([weather for _ in points],time)
            result=distribution(-33.5,20.5)
        self.assertEqual(result['summary']['sample_mean_kw'],2000)
        self.assertNotIn('total_kw',result['summary'])
        self.assertEqual(result['unique_weather_grid_points'],1)
        self.assertEqual(result['missing_samples'],0)

    def test_invalid_area_parameters(self):
        for kwargs in ({'level':'ward'},{'ahead':3},{'rated_kw':float('nan')}):
            with self.assertRaises(ValueError):
                distribution(-34,25,**kwargs)


if __name__=='__main__':
    unittest.main()
