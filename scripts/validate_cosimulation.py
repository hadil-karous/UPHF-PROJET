"""Bounded test using the repository's real CARLA/SUMO synchronizer."""
import csv, json, os, pathlib, sys, time, signal
import carla
import traci
sys.path.insert(0, '/tmp/exfmd-sumo')
from run_synchronization import SimulationSynchronization
from sumo_integration.carla_simulation import CarlaSimulation
from sumo_integration.sumo_simulation import SumoSimulation
out=pathlib.Path('/tmp/exfmd-cosim-results'); out.mkdir(exist_ok=True)
c=carla.Client('localhost',2000); c.set_timeout(60); w=c.get_world(); original=w.get_settings()
rows=[]; sync=None; sumo=None; report={}; start=time.monotonic()
def interrupted(signum, frame):
    raise KeyboardInterrupt("Stop requested")
signal.signal(signal.SIGTERM, interrupted)
try:
    if original.synchronous_mode: raise RuntimeError('Another tick owner is active')
    sumo=SumoSimulation('/tmp/exfmd-sumo/examples/uphf_piste/uphf_piste.sumocfg',0.05,None,None,False,1)
    cs=CarlaSimulation('localhost',2000,0.05); cs.client.set_timeout(60)
    sync=SimulationSynchronization(sumo,cs)
    for i in range(60):
        sync.tick()
        for sid,cid in sync.sumo2carla_ids.items():
            actor=w.get_actor(cid)
            if actor:
                pos=actor.get_location(); sa=sumo.get_actor(sid)
                rows.append([i,sid,cid,pos.x,pos.y,pos.z,traci.vehicle.getSpeed(sid)])
    report['mapped_sumo_ids']=sorted({r[1] for r in rows})
    report['mapped_samples']=len(rows)
    report['displacement_m']={}
    for sid in report['mapped_sumo_ids']:
        pts=[r for r in rows if r[1]==sid]
        report['displacement_m'][sid]=((pts[-1][3]-pts[0][3])**2+(pts[-1][4]-pts[0][4])**2)**0.5
    report['pass']=bool(rows) and max(report['displacement_m'].values())>1
except BaseException as e:
    report['error']=repr(e)
    raise
finally:
    if sync: sync.close()
    elif sumo: sumo.close()
    w.apply_settings(original)
    c.get_trafficmanager().set_synchronous_mode(False)
    report['wall_seconds']=time.monotonic()-start
    with (out/'positions.csv').open('w',newline='') as f:
        writer=csv.writer(f); writer.writerow(['step','sumo_id','carla_id','x','y','z','sumo_speed']); writer.writerows(rows)
    (out/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2),flush=True)


if not report.get("pass"): raise SystemExit("Co-simulation validation failed")
