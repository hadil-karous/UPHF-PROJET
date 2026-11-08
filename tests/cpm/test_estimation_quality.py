import importlib
import json
import math
from pathlib import Path
import sys
import types
import unittest
import tempfile
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'cosimulation'))
try:
    import carla
except ImportError:
    sys.modules['carla']=types.ModuleType('carla')
module=importlib.import_module('carla_multi_agent.fusion_detector')
from carla_multi_agent.perception_contract import snapshot, FrameAlignedWriter


def detection(x=0,actor=14):
    return dict(x=x,y=0.,z=0.,score=1.,object_id=actor,**{'class':'Car','class_id':1})


class EstimationQualityTests(unittest.TestCase):
    def setUp(self):
        module.KalmanTracker.count=0

    def test_initialization_never_claims_calibrated_velocity(self):
        tracker=module.KalmanTracker(detection())
        quality=tracker.get_state()['estimation_quality']
        self.assertEqual(quality['phase'],'initializing')
        self.assertEqual(quality['qualification'],'insufficient_observation')
        self.assertFalse(quality['velocity_available'])
        self.assertFalse(quality['physically_calibrated'])
        self.assertFalse(quality['legacy_score_is_probability'])

    def test_update_records_actual_innovation_and_correction(self):
        tracker=module.KalmanTracker(detection())
        tracker.predict(.05); predicted=tracker.x.copy(); covariance=tracker.P.copy()
        tracker.update(detection(1))
        q=tracker.get_state()['estimation_quality']; update=q['current_update']
        expected=np.array([1.,0.,0.])-tracker.H@predicted
        s=tracker.H@covariance@tracker.H.T+tracker.R
        np.testing.assert_allclose(update['innovation_world_m'],expected)
        self.assertAlmostEqual(update['normalized_innovation_squared_model'],float(expected@np.linalg.solve(s,expected)))
        np.testing.assert_allclose(update['position_correction_world_m'],(tracker.x-predicted)[:3])
        self.assertEqual(q['qualification'],'uncalibrated_estimate')
        self.assertNotEqual(q['qualification'],'reliable')

    def test_prediction_does_not_relabel_last_update_as_current(self):
        tracker=module.KalmanTracker(detection()); tracker.predict(.05); tracker.update(detection(1))
        last=tracker.get_state()['estimation_quality']['last_update']; velocity=tracker.x[3:].copy()
        tracker.predict(.05); tracker.misses+=1
        q=tracker.get_state()['estimation_quality']
        self.assertEqual(q['phase'],'prediction_only')
        self.assertEqual(q['qualification'],'insufficient_observation')
        self.assertIsNone(q['current_update'])
        self.assertEqual(q['consecutive_updates'],0)
        self.assertEqual(q['last_update'],last)
        self.assertAlmostEqual(q['last_measurement_age_s'],.05)
        np.testing.assert_array_equal(tracker.x[3:],velocity)

    def test_complete_empty_frames_expire_track(self):
        detector=module.FusionDetector.__new__(module.FusionDetector); detector._trackers=[]
        detector._update_trackers([detection()],dt=.05)
        for count in [1,2,3]:
            states=detector._update_trackers([],dt=.05)
            self.assertEqual(states[0]['misses'],count)
            self.assertEqual(states[0]['estimation_quality']['phase'],'prediction_only')
        self.assertEqual(detector._update_trackers([],dt=.05),[])

    def test_reacquisition_preserves_id_and_resets_measurement_age(self):
        detector=module.FusionDetector.__new__(module.FusionDetector); detector._trackers=[]
        first=detector._update_trackers([detection()],dt=.05)[0]
        detector._update_trackers([],dt=.05)
        state=detector._update_trackers([detection(.1)],dt=.05)[0]
        self.assertEqual(state['track_id'],first['track_id'])
        self.assertEqual(state['misses'],0)
        q=state['estimation_quality']
        self.assertEqual(q['last_measurement_age_s'],0)
        self.assertAlmostEqual(q['current_update']['measurement_interval_s'],.1)
        self.assertEqual(q['consecutive_updates'],1)

    def test_nonfinite_covariance_is_technical_not_normal(self):
        tracker=module.KalmanTracker(detection()); tracker.P[0,0]=math.nan
        q=tracker.get_state()['estimation_quality']
        self.assertEqual(q['qualification'],'technical_error')
        self.assertIsNone(q['model']['state_covariance_diagonal'])
        json.dumps(q,allow_nan=False)

    def test_large_update_is_visible_without_smoothing_or_normal_verdict(self):
        tracker=module.KalmanTracker(detection()); tracker.predict(.1); tracker.update(detection(20))
        q=tracker.get_state()['estimation_quality']
        self.assertGreater(abs(q['current_update']['position_correction_world_m'][0]),10)
        self.assertGreater(q['current_update']['normalized_innovation_squared_model'],1)
        self.assertFalse(q['physically_calibrated'])
        self.assertEqual(q['qualification'],'uncalibrated_estimate')

    def test_metadata_is_detached_and_survives_contract_without_confidence(self):
        tracker=module.KalmanTracker(detection()); state=tracker.get_state()
        def geo(v): return types.SimpleNamespace(latitude=math.degrees(v[1]/6335439.32729282),longitude=math.degrees(v[0]/6378137.),altitude=v[2])
        contract=snapshot([state],1,.1,(0,0,0),(1,0,0),geo)
        output=contract['objects'][0]
        self.assertIsNone(output['vx']); self.assertNotIn('velocity_confidence',output)
        self.assertNotIn('sensor_ids',output)
        output['estimation_quality']['reasons'].append('changed-copy')
        self.assertNotIn('changed-copy',state['estimation_quality']['reasons'])
        self.assertNotIn('changed-copy',tracker.get_state()['estimation_quality']['reasons'])

    def test_quality_does_not_change_the_original_kalman_equations(self):
        tracker=module.KalmanTracker(detection()); tracker.predict(.05)
        x=tracker.x.copy(); p=tracker.P.copy(); z=np.array([.2,0.,0.],dtype=np.float32)
        gain=p@tracker.H.T@np.linalg.inv(tracker.H@p@tracker.H.T+tracker.R)
        expected=x+gain@(z-tracker.H@x)
        tracker.update(detection(.2))
        np.testing.assert_array_equal(tracker.x,expected)

    def test_frame_join_preserves_quality_and_original_clock(self):
        quality=module.KalmanTracker(detection()).get_state()['estimation_quality']
        data={'schema_version':2,'time_base':'carla_simulation_seconds','frame_id':42,'measurement_time_s':100.,
            'objects':[{'track_id':7,'estimation_quality':quality}]}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'snapshot.json'; writer=FrameAlignedWriter(path)
            writer.register(42,.5); self.assertTrue(writer.publish(data))
            saved=json.loads(path.read_text())
            self.assertEqual(saved['objects'][0]['estimation_quality'],quality)
            self.assertEqual(saved['measurement_time_s'],.5)
            self.assertEqual(saved['carla_measurement_time_s'],100.)
            self.assertEqual(data['measurement_time_s'],100.)


if __name__=='__main__': unittest.main(verbosity=2)
