"""Small measured CARLA-only Gyrovia run; no ROS/V2X emulation."""
import argparse, csv, json, math, pathlib, queue, time, signal, os
import carla

p = argparse.ArgumentParser()
p.add_argument('--output', default='/tmp/exfmd-results')
p.add_argument('--steps', type=int, default=50)
a = p.parse_args()
out = pathlib.Path(a.output); out.mkdir(parents=True, exist_ok=True)
c = carla.Client('127.0.0.1', 2000); c.set_timeout(60)
w = c.get_world(); original = w.get_settings(); actors = []; counts = {}; rows = []
report = {'server': c.get_server_version(), 'map': w.get_map().name, 'v2x': 'unavailable', 'rsu': 'camera observation only, no V2X RSU'}
start = time.monotonic()
(out/'pid').write_text(str(os.getpid()))
def interrupted(signum, frame):
    raise KeyboardInterrupt('Stop requested')
signal.signal(signal.SIGTERM, interrupted)
try:
    if original.synchronous_mode:
        raise RuntimeError('World already synchronous: refusing to compete with another tick owner')
    s = w.get_settings(); s.synchronous_mode = True; s.fixed_delta_seconds = 0.05; w.apply_settings(s)
    bp = w.get_blueprint_library().find('vehicle.tesla.model3'); bp.set_attribute('role_name', 'exfmd_validation_hero')
    v = None
    for t in w.get_map().get_spawn_points():
        t.location.z += 0.5
        v = w.try_spawn_actor(bp, t)
        if v: break
    if not v: raise RuntimeError('No free spawn point')
    actors.append(v)
    v.set_simulate_physics(True)
    for _ in range(20): w.tick(60)
    initial = v.get_location()
    report['initial_position'] = [initial.x, initial.y, initial.z]
    report['blueprint'] = v.type_id
    camq = queue.Queue(maxsize=4)
    def image_cb(d):
        counts['rgb'] = counts.get('rgb', 0) + 1
        try: camq.put_nowait(d)
        except queue.Full: pass
    def sensor_cb(name):
        def cb(d):
            counts[name] = counts.get(name, 0) + 1
            if name == 'lidar' and counts[name] == 1: d.save_to_disk(str(out / 'lidar.ply'))
        return cb
    for name, kind, transform, attrs in [
        ('rgb', 'sensor.camera.rgb', carla.Transform(carla.Location(x=initial.x,y=initial.y,z=initial.z+12),carla.Rotation(pitch=-90)), {'image_size_x':'640','image_size_y':'360','sensor_tick':'0.2'}),
        ('lidar','sensor.lidar.ray_cast',carla.Transform(carla.Location(z=2.5)),{'channels':'16','points_per_second':'16000','range':'40','sensor_tick':'0.1'}),
        ('gnss','sensor.other.gnss',carla.Transform(carla.Location(z=2)),{}),
        ('imu','sensor.other.imu',carla.Transform(),{})]:
        b = w.get_blueprint_library().find(kind)
        for k,val in attrs.items(): b.set_attribute(k,val)
        sensor = w.spawn_actor(b, transform, **({} if name == 'rgb' else {'attach_to':v}))
        actors.append(sensor); sensor.listen(image_cb if name == 'rgb' else sensor_cb(name))
    for i in range(a.steps):
        v.apply_control(carla.VehicleControl(throttle=0.45, brake=0, hand_brake=False))
        frame = w.tick(60); snap = w.get_snapshot(); loc = v.get_location(); vel = v.get_velocity()
        rows.append([frame,snap.timestamp.elapsed_seconds,loc.x,loc.y,loc.z,math.sqrt(vel.x**2+vel.y**2+vel.z**2)])
        if not (out/'gyrovia_hero.png').exists():
            try: camq.get_nowait().save_to_disk(str(out/'gyrovia_hero.png'))
            except queue.Empty: pass
    time.sleep(1)
    if not (out/'gyrovia_hero.png').exists():
        try: camq.get(timeout=10).save_to_disk(str(out/'gyrovia_hero.png'))
        except queue.Empty: pass
    report['displacement_m'] = math.hypot(rows[-1][2]-initial.x,rows[-1][3]-initial.y)
    report['max_speed_m_s'] = max(r[5] for r in rows)
    report['max_height_deviation_m'] = max(abs(r[4]-initial.z) for r in rows)
    report['movement_pass'] = report['displacement_m'] > 1 and report['max_speed_m_s'] > 0.5 and report['max_height_deviation_m'] < 0.5
    report['sensor_callbacks'] = counts
    report['wall_seconds'] = time.monotonic()-start
    report['simulation_seconds'] = rows[-1][1]-rows[0][1]
    report['real_time_factor'] = report['simulation_seconds']/report['wall_seconds']
except BaseException as e:
    report['error'] = repr(e)
    raise
finally:
    for actor in reversed(actors):
        try:
            if actor.type_id.startswith('sensor.'): actor.stop()
            actor.destroy()
        except Exception as e: report.setdefault('cleanup_errors',[]).append(str(e))
    w.apply_settings(original)
    (out/'pid').unlink(missing_ok=True)
    with (out/'positions.csv').open('w',newline='') as f:
        writer=csv.writer(f); writer.writerow(['frame','simulation_seconds','x_m','y_m','z_m','speed_m_s']); writer.writerows(rows)
    (out/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2),flush=True)
if not report.get('movement_pass'): raise SystemExit('Movement validation failed')

