"""CPM v2 measurement contract. No ROS/CARLA dependencies.

ENU positions use WGS84 at the measured ego reference. Velocities are ground
velocities, never derivatives in the moving LiDAR frame. Unknown values stay null.
"""
import copy
import json
import math
import os
from pathlib import Path
import threading


def ecef(geo):
    lat, lon = math.radians(geo.latitude), math.radians(geo.longitude)
    a, e2 = 6378137.0, 6.69437999014e-3
    n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    h = geo.altitude
    return ((n + h) * math.cos(lat) * math.cos(lon),
            (n + h) * math.cos(lat) * math.sin(lon),
            (n * (1 - e2) + h) * math.sin(lat))


def enu(geo, reference):
    dx, dy, dz = (a - b for a, b in zip(ecef(geo), ecef(reference)))
    lat, lon = math.radians(reference.latitude), math.radians(reference.longitude)
    return (-math.sin(lon) * dx + math.cos(lon) * dy,
            -math.sin(lat) * math.cos(lon) * dx - math.sin(lat) * math.sin(lon) * dy + math.cos(lat) * dz,
            math.cos(lat) * math.cos(lon) * dx + math.cos(lat) * math.sin(lon) * dy + math.sin(lat) * dz)


def snapshot(states, frame_id, timestamp, reference_xyz, forward_xyz, to_geo):
    reference = to_geo(reference_xyz)
    forward = enu(to_geo(forward_xyz), reference)
    heading = math.degrees(math.atan2(forward[0], forward[1])) % 360
    objects = []
    for state in states:
        xyz = (state['x'], state['y'], state['z'])
        point = to_geo(xyz)
        position = enu(point, reference)
        obj = {k: state[k] for k in ('track_id', 'class', 'class_id', 'hits')}
        obj.update(zip(('x', 'y', 'z'), position))
        obj['vx'] = obj['vy'] = None
        if state['hits'] > 1:
            # Differential of the map georeference, not an assumed world Y sign.
            endpoint = to_geo((xyz[0] + state['vx'], xyz[1] + state['vy'], xyz[2] + state.get('vz', 0.0)))
            before = enu(point, reference)
            after = enu(endpoint, reference)
            obj['vx'], obj['vy'] = after[0] - before[0], after[1] - before[1]
        objects.append(obj)
    return {'schema_version': 2, 'frame': 'ENU', 'velocity_frame': 'ground_ENU',
            'time_base': 'carla_simulation_seconds', 'measurement_time_s': timestamp,
            'frame_id': frame_id, 'position_source': 'semantic_lidar_centroid',
            'reference': {'latitude': reference.latitude, 'longitude': reference.longitude,
                          'heading_deg': heading}, 'objects': objects, 'count': len(objects)}


class FrameAlignedWriter:
    """Join by CARLA frame, then atomically publish a SUMO-clock snapshot.

    The callback may arrive before or after frame registration. No latest-pose
    substitution, clock-zero guess, or overwrite by an older measurement.
    """
    def __init__(self, path, on_write=None):
        self.path = Path(path)
        self.times = {}
        self.pending = {}
        self.last_frame = -1
        self.lock = threading.RLock()
        self.on_write = on_write

    def register(self, frame_id, sumo_time):
        with self.lock:
            self.times[frame_id] = sumo_time
            if frame_id in self.pending:
                self.publish(self.pending.pop(frame_id))
            for table in (self.times, self.pending):
                for key in list(table):
                    if key < frame_id - 100:
                        del table[key]

    def publish(self, data):
        if data.get('schema_version') != 2 or data.get('time_base') != 'carla_simulation_seconds':
            raise ValueError('timestamped perception v2 required')
        with self.lock:
            frame = data['frame_id']
            if frame <= self.last_frame:
                return False
            if frame not in self.times:
                self.pending[frame] = copy.deepcopy(data)
                # Bound memory even if the consumer no longer registers frames.
                for key in sorted(self.pending)[:-100]:
                    del self.pending[key]
                return False
            result = copy.deepcopy(data)
            result['carla_measurement_time_s'] = result['measurement_time_s']
            result['measurement_time_s'] = self.times[frame]
            result['time_base'] = 'sumo_simulation_seconds'
            temporary = self.path.with_name(self.path.name + '.tmp')
            temporary.write_text(json.dumps(result, allow_nan=False), encoding='utf-8')
            os.replace(str(temporary), str(self.path))
            self.last_frame = frame
            if self.on_write is not None:
                self.on_write(copy.deepcopy(result))
            return True
