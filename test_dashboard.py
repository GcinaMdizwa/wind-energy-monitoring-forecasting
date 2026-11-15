"""Scientific boundary and local API tests; no public services required."""
import os
from pathlib import Path
import tempfile
import unittest

os.environ['WINDSCOPE_STATE'] = tempfile.mkdtemp(prefix='windscope-tests-')
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from dashboard_server import app
from recurrent_forecast import prepare, train, predict
from wind_data import power_curve


class DashboardTests(unittest.TestCase):
    def test_power_curve_boundaries(self):
        np.testing.assert_allclose(power_curve([0, 3, 12, 24.9, 25, 30]), [0, 0, 2000, 2000, 0, 0])

    def test_auth_and_project_isolation(self):
        a, b = TestClient(app), TestClient(app)
        self.assertEqual(a.get('/api/projects').status_code, 401)
        self.assertEqual(a.post('/api/auth/register',json={'name':'Research A','password':'local-test-password-A'}).status_code, 200)
        p = a.post('/api/projects',json={'name':'Coastal study','lat':-34,'lon':25,'rated_kw':2000}).json()
        self.assertEqual(len(a.get('/api/projects').json()['projects']),1)
        b.post('/api/auth/register',json={'name':'Research B','password':'local-test-password-B'})
        self.assertEqual(b.get('/api/projects').json()['projects'],[])
        self.assertEqual(b.get(f"/api/projects/{p['id']}/model").status_code,404)
        self.assertEqual(a.post('/api/projects',json={'name':'Bad coords','lat':100,'lon':25}).status_code,400)
        self.assertEqual(a.post('/api/logout',json={},headers={'Origin':'https://evil.example'}).status_code,403)
        a.post('/api/logout',json={})
        self.assertEqual(a.get('/api/projects').status_code,401)
        self.assertEqual(a.post('/api/auth/login',json={'name':'Research A','password':'wrong-password'}).status_code,401)
        self.assertEqual(a.post('/api/auth/login',json={'name':'Research A','password':'local-test-password-A'}).status_code,200)

    @staticmethod
    def frame():
        x=np.arange(1440)
        return pd.DataFrame({'timestamp':pd.date_range('2025-01-01',periods=len(x),freq='h',tz='UTC'),
                             'wind_speed_mps':7+np.sin(x/12), 'wind_direction_deg':(x*2)%360})

    def test_chronology_and_training_only_scaler(self):
        f=self.frame()
        _, mean, _, splits=prepare(f)
        self.assertAlmostEqual(float(mean[0]),f.wind_speed_mps.iloc[:1007].mean(),places=2)
        train_origin=splits[0][2]
        val_origin=splits[1][2]
        test_origin=splits[2][2]
        self.assertLess(train_origin[-1]+23,val_origin[0])
        self.assertLess(val_origin[-1]+23,test_origin[0])
        shifted=f.copy();shifted.loc[1224:,'wind_speed_mps']+=100
        np.testing.assert_allclose(prepare(shifted)[1],mean)

    def test_train_save_reload_forecast(self):
        with tempfile.TemporaryDirectory() as folder:
            frame=self.frame()
            report=train(frame,folder,{'source':'SYNTHETIC TEST ONLY'},epochs=2)
            self.assertEqual(report['epochs_run'],2)
            self.assertTrue(np.isfinite(report['model']['mae_mps']))
            forecast=predict(folder,frame.tail(48))
            self.assertEqual(len(forecast['rows']),24)
            self.assertGreater(pd.Timestamp(forecast['rows'][0]['time']),frame.timestamp.iloc[-1])
            self.assertTrue(all(r['power_kw']>=0 for r in forecast['rows']))

    def test_reject_missing_hours(self):
        with self.assertRaises(ValueError):
            prepare(self.frame().drop(index=800))


if __name__=='__main__':
    unittest.main()
