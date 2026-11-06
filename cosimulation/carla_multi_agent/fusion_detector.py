"""
fusion_detector.py — Fusion LiDAR sémantique + Caméra sémantique
Pipeline: projection LiDAR→image → coloured cloud → clustering → Kalman tracking
"""
import numpy as np
import threading
import math
import carla
import copy
import os
import json
from pathlib import Path
from .perception_contract import snapshot

# Tags sémantiques CARLA
VEHICLE_TAG    = 14
PEDESTRIAN_TAG = 4
BIKE_TAG       = 18  # bicycle

CLASS_MAP = {
    VEHICLE_TAG:    ('Car',        1),
    PEDESTRIAN_TAG: ('Pedestrian', 2),
    BIKE_TAG:       ('Cyclist',    3),
}

DETECTION_TAGS = set(CLASS_MAP.keys())


class KalmanTracker:
    count = 0

    def __init__(self, obj):
        self.id = KalmanTracker.count
        KalmanTracker.count += 1
        dt = 0.1
        self.x = np.array([obj['x'], obj['y'], obj['z'], 0., 0., 0.], dtype=np.float32)
        self.F = np.eye(6, dtype=np.float32)
        self.F[0,3] = self.F[1,4] = self.F[2,5] = dt
        self.H = np.eye(3, 6, dtype=np.float32)
        self.P = np.eye(6, dtype=np.float32) * 10
        self.Q = np.eye(6, dtype=np.float32) * 0.1
        self.R = np.eye(3, dtype=np.float32) * 0.5
        self.hits   = 1
        self.misses = 0
        self.cls    = obj['class']
        self.cls_id = obj['class_id']
        self.score  = obj['score']
        self.source_object_id = obj.get('object_id')

    def predict(self, dt=0.1):
        self.F[0,3] = self.F[1,4] = self.F[2,5] = dt
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q

    def update(self, obj):
        z = np.array([obj['x'], obj['y'], obj['z']], dtype=np.float32)
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x  = self.x + K @ y
        self.P  = (np.eye(6) - K @ self.H) @ self.P
        self.hits  += 1
        self.misses = 0
        self.source_object_id = obj.get('object_id')

    def get_state(self):
        return {
            'x':         float(self.x[0]),
            'y':         float(self.x[1]),
            'z':         float(self.x[2]),
            'vx':        float(self.x[3]),
            'vy':        float(self.x[4]),
            'vz':        float(self.x[5]),
            'distance':  float(math.sqrt(self.x[0]**2 + self.x[1]**2)),
            'velocity':  float(math.sqrt(self.x[3]**2 + self.x[4]**2)),
            'class':     self.cls,
            'class_id':  self.cls_id,
            'score':     1.0,
            'track_id':  self.id,
            'hits':      self.hits,
            'misses':    self.misses,
            'source_object_id': self.source_object_id,
        }


class FusionDetector:
    def __init__(self, world, hero, cfg):
        self.world  = world
        self._map = world.get_map()
        self.hero   = hero
        self._lock  = threading.Lock()

        # Données capteurs
        self._lidar_data  = None
        self._sem_img     = None
        self._calib       = None  # matrice de projection

        # Trackers
        self._trackers = []
        self._latest   = []
        self._latest_snapshot = None
        self._measurement_time = None
        self._fusion_lock = threading.Lock()
        trace = os.environ.get('EXFMD_FUSION_TRACE_DIR')
        self._trace_dir = Path(trace) if trace else None
        if self._trace_dir is not None:
            self._trace_dir.mkdir(parents=True, exist_ok=True)

        # Attacher les sensors
        self._sensors = []
        self._attach(cfg)

    def _attach(self, cfg):
        bp_lib = self.world.get_blueprint_library()
        w = cfg['sensors']['camera']['width']
        h = cfg['sensors']['camera']['height']
        fov = cfg['sensors']['camera']['fov']

        # Caméra sémantique
        bp_cam = bp_lib.find('sensor.camera.semantic_segmentation')
        bp_cam.set_attribute('image_size_x', str(w))
        bp_cam.set_attribute('image_size_y', str(h))
        bp_cam.set_attribute('fov', str(fov))
        cam = self.world.spawn_actor(
            bp_cam,
            carla.Transform(carla.Location(x=2.0, z=1.4)),
            attach_to=self.hero
        )
        cam.listen(self._on_sem_cam)
        self._sensors.append(cam)

        # Matrice de projection intrinsèque
        focal = w / (2.0 * math.tan(math.radians(fov) / 2.0))
        self._K = np.array([
            [focal, 0,     w / 2.0],
            [0,     focal, h / 2.0],
            [0,     0,     1.0    ]
        ], dtype=np.float32)
        self._img_w = w
        self._img_h = h

        # LiDAR sémantique
        bp_lid = bp_lib.find('sensor.lidar.ray_cast_semantic')
        bp_lid.set_attribute('channels',           str(cfg['sensors']['lidar']['channels']))
        bp_lid.set_attribute('range',              str(cfg['sensors']['lidar']['range']))
        bp_lid.set_attribute('points_per_second',  str(cfg['sensors']['lidar']['points_per_second']))
        bp_lid.set_attribute('rotation_frequency', str(cfg['sensors']['lidar']['rotation_frequency']))
        bp_lid.set_attribute('upper_fov', '2.0')
        bp_lid.set_attribute('lower_fov', '-26.0')
        lid = self.world.spawn_actor(
            bp_lid,
            carla.Transform(carla.Location(z=2.5)),
            attach_to=self.hero
        )
        lid.listen(self._on_lidar)
        self._sensors.append(lid)

        print(f'[FusionDetector] Sensors attachés sur {self.hero.type_id}')

    def _on_sem_cam(self, image):
        # image.raw_data: BGRA où B=tag, G=0, R=0, A=255
        arr = np.frombuffer(image.raw_data, dtype=np.uint8)
        arr = arr.reshape((image.height, image.width, 4))
        with self._lock:
            self._sem_img = arr[:, :, 2].copy()  # canal R = semantic tag

    def _on_lidar(self, data):
        pts = np.frombuffer(data.raw_data, dtype=np.dtype([
            ('x', np.float32), ('y', np.float32), ('z', np.float32),
            ('cos_inc_angle', np.float32),
            ('object_idx', np.uint32),
            ('semantic_tag', np.uint32)
        ]))
        with self._fusion_lock:
            if self._measurement_time is not None and data.timestamp <= self._measurement_time:
                return
            dt = data.timestamp - self._measurement_time if self._measurement_time is not None else 0.1
            self._measurement_time = data.timestamp
            with self._lock:
                self._lidar_data = pts.copy()
            self._fuse_and_track(data, dt)

    def _fuse_and_track(self, measurement, dt):
        with self._lock:
            if self._lidar_data is None:
                return
            pts      = self._lidar_data
            sem_img  = self._sem_img

        # Filtrer points des objets d'intérêt
        mask = np.isin(pts['semantic_tag'], list(DETECTION_TAGS))
        pts  = pts[mask]

        # Grouper par object_idx → centroïde
        raw_objects = []
        for obj_id in np.unique(pts['object_idx']):
            if obj_id == 0:
                continue
            actor = self.world.get_actor(int(obj_id))
            if actor is None or actor.id == self.hero.id:
                continue
            m    = pts['object_idx'] == obj_id
            tag  = int(pts['semantic_tag'][m][0])
            xs, ys, zs = pts['x'][m], pts['y'][m], pts['z'][m]
            if len(xs) < 2:
                continue
            cx, cy, cz = float(np.mean(xs)), float(np.mean(ys)), float(np.mean(zs))
            dist = math.sqrt(cx**2 + cy**2)
            if dist > 55 or dist < 0.5:
                continue
            cls_name, cls_id = CLASS_MAP.get(tag, ('Car', 1))

            # Enrichir avec caméra sémantique si disponible
            if sem_img is not None:
                cam_cls = self._get_camera_class(xs, ys, zs, sem_img)
                if cam_cls is not None:
                    cls_name, cls_id = cam_cls

            # The sensor pose belongs to this measurement, not to the latest tick.
            centre = measurement.transform.transform(carla.Location(x=cx, y=cy, z=cz))
            raw_objects.append({
                'x': centre.x, 'y': centre.y, 'z': centre.z,
                'distance': dist,
                'class': cls_name, 'class_id': cls_id,
                'score': 1.0, 'object_id': int(obj_id),
            })

        # Kalman tracking
        tracked = self._update_trackers(raw_objects, dt=dt)
        # Sensor mount is (0,0,2.5), without relative rotation. Reference is the
        # bottom/front centre of the known ego bounding box (ground approximation).
        box = self.hero.bounding_box
        reference = measurement.transform.transform(carla.Location(
            x=box.location.x + box.extent.x, y=box.location.y,
            z=box.location.z - box.extent.z - 2.5))
        forward = measurement.transform.transform(carla.Location(
            x=box.location.x + box.extent.x + 1.0, y=box.location.y,
            z=box.location.z - box.extent.z - 2.5))
        def to_geo(xyz):
            return self._map.transform_to_geolocation(carla.Location(x=xyz[0], y=xyz[1], z=xyz[2]))
        contract = snapshot(tracked, measurement.frame, measurement.timestamp,
            (reference.x, reference.y, reference.z), (forward.x, forward.y, forward.z), to_geo)
        if getattr(self, '_trace_dir', None) is not None:
            def geo_dict(xyz):
                value=to_geo(xyz)
                return dict(latitude=value.latitude,longitude=value.longitude,altitude=value.altitude)
            evidence={'frame_id':measurement.frame,'measurement_time_s':measurement.timestamp,
                'sensor_transform':measurement.transform.get_matrix(),
                'reference_world':[reference.x,reference.y,reference.z],
                'reference_geo':geo_dict((reference.x,reference.y,reference.z)),
                'forward_geo':geo_dict((forward.x,forward.y,forward.z)),
                'raw_detections_world':raw_objects,'tracked_world':tracked,'contract':contract,
                'tracked_geo':[geo_dict((s['x'],s['y'],s['z'])) for s in tracked],
                'velocity_endpoint_geo':[geo_dict((s['x']+s['vx'],s['y']+s['vy'],s['z']+s['vz'])) for s in tracked]}
            (self._trace_dir/('frame-'+str(measurement.frame)+'.json')).write_text(json.dumps(evidence,allow_nan=False))
        # Keep the legacy display positions local; CPM uses only the labelled snapshot.
        inverse = np.array(measurement.transform.get_inverse_matrix())
        display = []
        for state in tracked:
            state = dict(state)
            local = inverse @ np.array([state['x'], state['y'], state['z'], 1.0])
            state.update(x=float(local[0]), y=float(local[1]), z=float(local[2]))
            state['distance'] = math.hypot(state['x'], state['y'])
            display.append(state)
        with self._lock:
            self._latest = display
            self._latest_snapshot = contract

    def _get_camera_class(self, xs, ys, zs, sem_img):
        """Projeter les points LiDAR sur l'image et lire le tag caméra."""
        try:
            pts3d = np.stack([xs, ys, zs], axis=1)
            # LiDAR frame: x=forward, y=right, z=up → caméra: x=right, y=down, z=forward
            pts_cam = np.stack([pts3d[:,1], -pts3d[:,2], pts3d[:,0]], axis=1)
            # Garder points devant la caméra
            front = pts_cam[:,2] > 0
            if not np.any(front):
                return None
            pts_cam = pts_cam[front]
            # Projection
            uvw = (self._K @ pts_cam.T).T
            u   = (uvw[:,0] / uvw[:,2]).astype(int)
            v   = (uvw[:,1] / uvw[:,2]).astype(int)
            # Filtrer dans l'image
            valid = (u >= 0) & (u < self._img_w) & (v >= 0) & (v < self._img_h)
            if not np.any(valid):
                return None
            tags = sem_img[v[valid], u[valid]]
            # Tag majoritaire
            unique, counts = np.unique(tags, return_counts=True)
            dominant_tag   = int(unique[np.argmax(counts)])
            return CLASS_MAP.get(dominant_tag, None)
        except Exception:
            return None

    def _update_trackers(self, detections, max_dist=5.0, max_misses=3, min_hits=1, dt=0.1):
        for t in self._trackers:
            t.predict(dt)

        if not self._trackers:
            for d in detections:
                self._trackers.append(KalmanTracker(d))
        elif detections:
            # Nearest Neighbour association
            cost = np.zeros((len(self._trackers), len(detections)))
            for i, t in enumerate(self._trackers):
                for j, d in enumerate(detections):
                    cost[i,j] = math.sqrt((t.x[0]-d['x'])**2 + (t.x[1]-d['y'])**2)

            matched_t, matched_d = set(), set()
            while True:
                if cost.size == 0:
                    break
                idx = np.unravel_index(np.argmin(cost), cost.shape)
                i, j = idx
                if cost[i,j] > max_dist:
                    break
                self._trackers[i].update(detections[j])
                matched_t.add(i)
                matched_d.add(j)
                cost[i,:] = np.inf
                cost[:,j] = np.inf

            for i, t in enumerate(self._trackers):
                if i not in matched_t:
                    t.misses += 1

            for j, d in enumerate(detections):
                if j not in matched_d:
                    self._trackers.append(KalmanTracker(d))

        self._trackers = [t for t in self._trackers if t.misses <= max_misses]
        return [t.get_state() for t in self._trackers if t.hits >= min_hits]

    def detect(self):
        with self._lock:
            return list(self._latest)

    def perception_snapshot(self):
        with self._lock:
            return copy.deepcopy(self._latest_snapshot)

    def destroy(self):
        for s in self._sensors:
            if s and s.is_alive:
                s.stop()
                s.destroy()
