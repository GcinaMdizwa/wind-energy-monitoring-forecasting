"""Checks for time leakage, data validation and baseline correctness."""
import unittest
import numpy as np
import pandas as pd
from wind_forecast import demo_data, evaluate, features, metrics, validate


class ForecastTests(unittest.TestCase):
    def test_features_do_not_read_future(self):
        frame = demo_data(300)
        original = features(frame)
        frame.loc[151:, ["power_kw", "wind_speed_mps", "wind_direction_deg"]] = 99
        pd.testing.assert_frame_equal(original.loc[:150], features(frame).loc[:150])

    def test_purged_holdout_and_actual_target(self):
        frame = demo_data(300)
        summary, result = evaluate(frame, 6)
        self.assertLess(pd.Timestamp(summary["training_last_target_time"]),
                        pd.Timestamp(summary["test_first_issue_time"]))
        self.assertTrue((result.target_time - result.issue_time == pd.Timedelta(hours=6)).all())
        indexed = frame.set_index("timestamp")
        np.testing.assert_allclose(result.actual_power_kw, indexed.loc[result.target_time, "power_kw"])
        np.testing.assert_allclose(result.persistence_power_kw, indexed.loc[result.issue_time, "power_kw"])

    def test_reject_duplicate_and_irregular_times(self):
        frame = demo_data(300)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate(pd.concat([frame, frame.iloc[[0]]]))
        with self.assertRaisesRegex(ValueError, "regular"):
            validate(frame.drop(index=30))

    def test_reject_missing_nonfinite_and_bad_horizon(self):
        frame = demo_data(300)
        with self.assertRaisesRegex(ValueError, "Missing"):
            validate(frame.drop(columns="power_kw"))
        frame.loc[0, "wind_speed_mps"] = np.inf
        with self.assertRaisesRegex(ValueError, "Non-finite"):
            validate(frame)
        with self.assertRaisesRegex(ValueError, "horizon"):
            evaluate(demo_data(300), 0)

    def test_metrics_units(self):
        self.assertEqual(metrics(np.array([1., 3.]), np.array([2., 2.])),
                         {"mae_kw": 1., "rmse_kw": 1.})


if __name__ == "__main__":
    unittest.main()
