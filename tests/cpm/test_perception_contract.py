import importlib
import json
import math
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock
import hashlib

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'cosimulation'))
from carla_multi_agent.perception_contract import snapshot, FrameAlignedWriter, enu


def geo(xyz):
    # Equatorial analytic map, X East and Y South, matching CARLA handedness.
    return types.SimpleNamespace(latitude=math.degrees(-xyz[1]/6335439.32729282),
        longitude=math.degrees(xyz[0]/6378137.0), altitude=xyz[2])


class ContractTests(unittest.TestCase):
    def state(self, **kwargs):
        state = dict(x=10.,y=0.,z=0.,vx=-3.,vy=-4.,vz=0.,track_id=71,
                     hits=2,**{'class':'Pedestrian','class_id':2})
        state.update(kwargs)
        return state

    def test_enu_ground_signed_velocity_and_id(self):
        obj=snapshot([self.state()],42,3.,(0,0,0),(1,0,0),geo)['objects'][0]
        self.assertEqual(obj['track_id'],71)
        self.assertAlmostEqual(obj['x'],10,places=3)
        self.assertAlmostEqual(obj['vx'],-3,places=3)
        self.assertAlmostEqual(obj['vy'],4,places=3)
        self.assertNotIn('length',obj)
        self.assertNotIn('ax',obj)

    def test_ego_translation_does_not_change_ground_velocity(self):
        a=snapshot([self.state(vx=0,vy=0)],1,1.,(0,0,0),(1,0,0),geo)
        b=snapshot([self.state(vx=0,vy=0)],2,2.,(5,0,0),(6,0,0),geo)
        self.assertAlmostEqual(a['objects'][0]['x']-b['objects'][0]['x'],5,places=3)
        self.assertAlmostEqual(b['objects'][0]['vx'],0,places=6)

    def test_heading_rotation_does_not_rotate_enu_velocity(self):
        a=snapshot([self.state()],1,1.,(0,0,0),(0,-1,0),geo)
        b=snapshot([self.state()],1,1.,(0,0,0),(1,0,0),geo)
        self.assertAlmostEqual(a['reference']['heading_deg'],0,places=3)
        self.assertAlmostEqual(b['reference']['heading_deg'],90,places=3)
        self.assertEqual(a['objects'],b['objects'])

    def test_first_hit_velocity_unknown(self):
        obj=snapshot([self.state(hits=1)],1,1.,(0,0,0),(1,0,0),geo)['objects'][0]
        self.assertIsNone(obj['vx']); self.assertIsNone(obj['vy'])

    def test_frame_join_both_arrival_orders_and_atomic_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'perceived_0'; writer=FrameAlignedWriter(path)
            data=snapshot([self.state()],42,101.,(0,0,0),(1,0,0),geo)
            self.assertFalse(writer.publish(data)); self.assertFalse(path.exists())
            writer.register(42,.4)
            saved=json.loads(path.read_text())
            self.assertEqual(saved['measurement_time_s'],.4)
            self.assertEqual(saved['carla_measurement_time_s'],101.)
            self.assertEqual(data['measurement_time_s'],101.)
            self.assertFalse(writer.publish(data))
            writer.register(43,.5); data['frame_id']=43
            self.assertTrue(writer.publish(data))
            self.assertFalse(path.with_name('perceived_0.tmp').exists())

    def test_reject_unversioned(self):
        with self.assertRaises(ValueError): FrameAlignedWriter('unused').publish({'objects':[]})

    def test_archive_callback_observes_exact_frame_join(self):
        with tempfile.TemporaryDirectory() as directory:
            archived=[]; path=Path(directory)/'perceived_0'
            writer=FrameAlignedWriter(path,archived.append)
            data=snapshot([self.state()],42,101.,(0,0,0),(1,0,0),geo)
            writer.publish(data); self.assertEqual(archived,[])
            writer.register(42,.4)
            self.assertEqual(archived,[json.loads(path.read_text())])
            self.assertEqual(archived[0]['frame_id'],42)
            self.assertEqual(archived[0]['carla_measurement_time_s'],101.)
            self.assertEqual(archived[0]['measurement_time_s'],.4)

    def test_runtime_rejects_missing_or_stale_component(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
        from cpm.runtime import validated_core
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); build=root/'results/phase1/corrections'; build.mkdir(parents=True)
            with self.assertRaises(RuntimeError): validated_core(root)
            core=build/'libartery_core.so'; core.write_bytes(b'test artifact')
            source=root/'source.cc'; source.write_bytes(b'source')
            manifest={'source_hashes':{'source.cc':hashlib.sha256(source.read_bytes()).hexdigest()},
                'patched_core_sha256':hashlib.sha256(core.read_bytes()).hexdigest()}
            (build/'component-build.json').write_text(json.dumps(manifest))
            self.assertEqual(validated_core(root),core)
            source.write_bytes(b'changed')
            with self.assertRaises(RuntimeError): validated_core(root)

    def test_actual_kalman_uses_elapsed_time(self):
        # Only the unavailable CARLA module is stubbed; actual NumPy tracker runs.
        try: import carla
        except ImportError: sys.modules['carla']=types.ModuleType('carla')
        module=importlib.import_module('carla_multi_agent.fusion_detector')
        tracker=module.KalmanTracker(dict(x=0,y=0,z=0,score=1,**{'class':'Car','class_id':1}))
        tracker.x[3]=2
        tracker.predict(.25)
        self.assertAlmostEqual(tracker.x[0],.5)
        self.assertAlmostEqual(tracker.F[0,3],.25)

    def test_tracker_records_actual_source_assignment(self):
        try: import carla
        except ImportError: sys.modules['carla']=types.ModuleType('carla')
        module=importlib.import_module('carla_multi_agent.fusion_detector')
        detection=dict(x=1,y=2,z=3,score=1,object_id=42,**{'class':'Car','class_id':1})
        tracker=module.KalmanTracker(detection)
        self.assertEqual(tracker.get_state()['source_object_id'],42)
        tracker.predict(.1); tracker.misses+=1
        self.assertEqual(tracker.get_state()['source_object_id'],42)
        self.assertEqual(tracker.get_state()['misses'],1)
        tracker.update(detection)
        self.assertEqual(tracker.get_state()['misses'],0)

    def test_actual_lidar_callback_compensates_translation_and_rotation(self):
        try: import carla
        except ImportError: sys.modules['carla']=types.ModuleType('carla')
        module=importlib.import_module('carla_multi_agent.fusion_detector')
        import numpy as np
        import threading
        def location(x=0,y=0,z=0): return types.SimpleNamespace(x=x,y=y,z=z)
        class Transform:
            def __init__(self, x, angle):
                c,s=math.cos(angle),math.sin(angle)
                self.matrix=np.array([[c,-s,0,x],[s,c,0,0],[0,0,1,2.5],[0,0,0,1.]])
            def transform(self, p):
                v=self.matrix @ np.array([p.x,p.y,p.z,1.])
                return location(*v[:3])
            def get_inverse_matrix(self): return np.linalg.inv(self.matrix)
        detector=object.__new__(module.FusionDetector)
        detector._lock=threading.Lock(); detector._fusion_lock=threading.Lock()
        detector._measurement_time=None; detector._lidar_data=None
        detector._sem_img=None; detector._trackers=[]; detector._latest=[]
        detector._latest_snapshot=None
        detector.hero=types.SimpleNamespace(id=1,bounding_box=types.SimpleNamespace(
            location=location(),extent=location(2.,1.,0.)))
        detector.world=types.SimpleNamespace(get_actor=lambda i:types.SimpleNamespace(id=i),
            get_map=lambda:types.SimpleNamespace(transform_to_geolocation=lambda p:geo((p.x,p.y,p.z))))
        detector._map=detector.world.get_map()
        dtype=np.dtype([('x',np.float32),('y',np.float32),('z',np.float32),
            ('cos_inc_angle',np.float32),('object_idx',np.uint32),('semantic_tag',np.uint32)])
        snapshots=[]
        with mock.patch.object(module.carla,'Location',side_effect=location,create=True):
            for i in range(5):
                transform=Transform(i*.2,i*.1)
                local=transform.get_inverse_matrix() @ np.array([10.,0.,0.,1.])
                points=np.array([tuple(local[:3])+(1.,2,14)]*3,dtype=dtype)
                measurement=types.SimpleNamespace(timestamp=.1*(i+1),frame=i+100,
                    transform=transform,raw_data=points.tobytes())
                detector._on_lidar(measurement)
                snapshots.append(detector.perception_snapshot())
        ids=[s['objects'][0]['track_id'] for s in snapshots]
        self.assertEqual(len(set(ids)),1)
        self.assertEqual(snapshots[-1]['frame_id'],104)
        self.assertEqual(snapshots[-1]['measurement_time_s'],.5)
        self.assertAlmostEqual(snapshots[-1]['objects'][0]['vx'],0,places=3)
        self.assertAlmostEqual(snapshots[-1]['objects'][0]['vy'],0,places=3)
        self.assertAlmostEqual(detector._trackers[0].x[0],10,places=3)


if __name__=='__main__': unittest.main(verbosity=2)
