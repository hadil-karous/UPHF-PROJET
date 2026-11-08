import importlib
import math
from pathlib import Path
import sys
import types
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'cosimulation')]
try: import carla
except ImportError: sys.modules['carla']=types.ModuleType('carla')
from experiments.tracker_a34 import ExperimentalTracker,Settings,process_covariance
from carla_multi_agent.fusion_detector import KalmanTracker


def observation(p):
    return dict(x=float(p[0]),y=float(p[1]),z=0.,object_id=14,score=1.,**{'class':'Car','class_id':1})


class TrackerA34Tests(unittest.TestCase):
    def test_legacy_variant_exactly_reproduces_production(self):
        a=KalmanTracker(observation((0,0))); b=ExperimentalTracker(observation((0,0)),Settings('baseline'))
        for i in range(20):
            dt=[.03,.05,.12][i%3]
            a.predict(dt); b.predict(dt)
            if i%4:
                a.update(observation((i*.2,0))); b.update(observation((i*.2,0)))
            np.testing.assert_array_equal(a.x,b.x); np.testing.assert_array_equal(a.P,b.P)

    def test_continuous_q_has_consistent_units_and_cross_terms(self):
        q=process_covariance(.1,2.)
        self.assertAlmostEqual(q[0,0],2*.1**3/3)
        self.assertAlmostEqual(q[0,3],2*.1**2/2)
        self.assertAlmostEqual(q[3,3],.2)
        self.assertGreaterEqual(np.linalg.eigvalsh(q).min(),0)

    def test_continuous_covariance_composes_across_unequal_intervals(self):
        a,b=.03,.17
        f=np.eye(6); f[:3,3:]=np.eye(3)*b
        np.testing.assert_allclose(process_covariance(a+b,2.),f@process_covariance(a,2.)@f.T+process_covariance(b,2.),atol=1e-15)

    def test_missing_measurement_predicts_without_creating_a_measurement(self):
        tracker=ExperimentalTracker(observation((0,0)),Settings('cwa','continuous',2.))
        tracker.x[3]=3
        tracker.predict(.2); tracker.misses+=1
        self.assertAlmostEqual(tracker.x[0],.6,places=6)
        self.assertEqual(tracker.get_state()['estimation_quality']['phase'],'prediction_only')
        self.assertIsNone(tracker.get_state()['estimation_quality']['current_update'])
        self.assertFalse(tracker.get_state()['estimation_quality']['physically_calibrated'])

    def test_curved_trajectory_variable_time_stays_finite_and_responsive(self):
        tracker=ExperimentalTracker(observation((8,0)),Settings('cwa','continuous',2.))
        t=0
        for i in range(160):
            dt=[.025,.05,.075][i%3]; t+=dt
            tracker.predict(dt)
            if i%13:
                tracker.update(observation((8*math.cos(.2*t),8*math.sin(.2*t))))
            else: tracker.misses+=1
            self.assertTrue(np.isfinite(tracker.x).all())
            self.assertGreaterEqual(np.linalg.eigvalsh(tracker.P).min(),-1e-9)
        self.assertGreater(np.linalg.norm(tracker.x[3:5]),.5)
        self.assertLess(np.linalg.norm(tracker.x[:2]-[8*math.cos(.2*t),8*math.sin(.2*t)]),1.)

    def test_large_innovation_is_not_silently_clipped_or_called_reliable(self):
        tracker=ExperimentalTracker(observation((0,0)),Settings('cwa','continuous',2.))
        for _ in range(30): tracker.predict(.05); tracker.update(observation((0,0)))
        tracker.predict(.05); tracker.update(observation((20,0)))
        quality=tracker.get_state()['estimation_quality']
        self.assertGreater(quality['current_update']['normalized_innovation_squared_model'],100)
        self.assertGreater(abs(tracker.x[0]),.1)
        self.assertEqual(quality['qualification'],'uncalibrated_estimate')

    def test_invalid_intervals_and_parameters_rejected(self):
        for dt in [0,-1,math.nan]:
            with self.assertRaises(ValueError): process_covariance(dt,2.)
        with self.assertRaises(ValueError): ExperimentalTracker(observation((0,0)),Settings('bad',r=-1))


if __name__=='__main__': unittest.main(verbosity=2)
