"""A3.3: paired replay of the real old/new tracker and archived geometry.

No CARLA/ROS process. Archived geographic lookup is used only at saved points;
it is not a new map/georeference or an independent sensor measurement.
"""
import argparse,collections,copy,csv,hashlib,importlib,importlib.util,json,math,pathlib,sys,types
import numpy as np
root=pathlib.Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(); parser.add_argument('--case',required=True); parser.add_argument('--label',default='analysis'); args=parser.parse_args()
assert args.label.startswith('analysis') and '/' not in args.label and '\\' not in args.label
case=root/args.case; out=case/args.label; out.mkdir(exist_ok=False)
a1=root/'results/phase1/a1-e2e-20261106-161848/attempt-02'
cal=root/'results/phase3/calibration-20261108-190113'; native=cal/'native-20261108-181019-177625'
def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def norm(v): return math.hypot(float(v[0]),float(v[1]))
sys.path.insert(0,str(root/'cosimulation')); sys.modules['carla']=types.ModuleType('carla')
current=importlib.import_module('carla_multi_agent.fusion_detector')
spec=importlib.util.spec_from_file_location('carla_multi_agent.fusion_detector_before_a33',case/'before-sources/fusion_detector.py')
frozen=importlib.util.module_from_spec(spec); spec.loader.exec_module(frozen)
contract_spec=importlib.util.spec_from_file_location('perception_contract_before_a33',case/'before-sources/perception_contract.py')
frozen_contract=importlib.util.module_from_spec(contract_spec); contract_spec.loader.exec_module(frozen_contract)
from carla_multi_agent.perception_contract import snapshot
old=frozen.FusionDetector.__new__(frozen.FusionDetector); old._trackers=[]; frozen.KalmanTracker.count=0
new=current.FusionDetector.__new__(current.FusionDetector); new._trackers=[]; current.KalmanTracker.count=0
frames={load(p)['frame_id']:load(p) for p in (a1/'fusion').glob('*.json')}
timings={r['frame_id']:r for r in map(json.loads,(a1/'frame-times.jsonl').read_text().splitlines())}
poses={}
for r in csv.DictReader((a1/'positions.csv').open()):
    poses[(int(r['carla_frame']),r['sumo_id'])]={k:float(r[k]) for k in ['x','y','z','speed_m_s','sumo_time']}
new_snapshots={}; diagnostics={}; errors=[]; covariance_errors=[]; geographic_recompute_errors=[]; last=None
(out/'snapshots').mkdir()
def compare_numeric(a,b):
    if isinstance(a,dict):
        assert set(a)==set(b)
        for k in a: compare_numeric(a[k],b[k])
    elif isinstance(a,list):
        assert len(a)==len(b)
        for x,y in zip(a,b): compare_numeric(x,y)
    elif isinstance(a,(float,int)) and isinstance(b,(float,int)):
        geographic_recompute_errors.append(abs(a-b)); assert abs(a-b)<2e-8,(a,b)
    else: assert a==b
for frame,f in sorted(frames.items()):
    dt=f['measurement_time_s']-last if last is not None else .1; last=f['measurement_time_s']
    previous={t.id:t.x.copy() for t in new._trackers}
    before=old._update_trackers(f['raw_detections_world'],dt=dt)
    after=new._update_trackers(f['raw_detections_world'],dt=dt)
    assert len(before)==len(after)==len(f['tracked_world'])
    for a,b,saved in zip(before,after,f['tracked_world']):
        assert {k:v for k,v in b.items() if k!='estimation_quality'}==a
        errors.extend(abs(a[k]-saved[k]) for k in ['x','y','z','vx','vy','vz'])
        covariance_errors.extend(abs(x-y) for x,y in zip(old._trackers[a['track_id']].P.flat,new._trackers[b['track_id']].P.flat))
        q=b['estimation_quality']; tracker=next(t for t in new._trackers if t.id==b['track_id'])
        raw=next((d for d in f['raw_detections_world'] if d['object_id']==b['source_object_id']),None)
        diagnostics[(frame,b['track_id'])]={'frame_id':frame,'track_id':b['track_id'],'actor_id':b['source_object_id'],
            'state_world':b,'quality':q,'raw_detection':raw,'model_covariance_world':tracker.P.tolist(),
            'sensor_step_s':dt,'reference_geo':f['reference_geo']}
        assert q['physically_calibrated'] is False
    # Replay snapshot() at the saved geographic points; no invented map mapping.
    geo={tuple(f['reference_world']):f['reference_geo']}
    ref=tuple(f['reference_world']); forward=(ref[0]+1.,ref[1],ref[2]); geo[forward]=f['forward_geo']
    for state,g,e in zip(after,f['tracked_geo'],f['velocity_endpoint_geo']):
        xyz=tuple(state[k] for k in ['x','y','z']); geo[xyz]=g
        geo[tuple(state[k]+state[v] for k,v in [('x','vx'),('y','vy'),('z','vz')])]=e
    contract=snapshot(after,frame,f['measurement_time_s'],ref,forward,lambda xyz:types.SimpleNamespace(**geo[tuple(xyz)]))
    stripped=copy.deepcopy(contract)
    for o in stripped['objects']: o.pop('estimation_quality')
    old_contract=frozen_contract.snapshot(before,frame,f['measurement_time_s'],ref,forward,lambda xyz:types.SimpleNamespace(**geo[tuple(xyz)]))
    assert stripped==old_contract, 'old/new physical snapshot changed at frame '+str(frame)
    compare_numeric(stripped,f['contract'])
    new_snapshots[frame]=contract
    (out/'snapshots'/('frame-%d.json'%frame)).write_text(json.dumps(contract,indent=2,allow_nan=False))
assert max(errors)==0 and max(covariance_errors)==0
controls=load(native/'offline-controls.json'); by_key={(r['provenance']['receiver'],r['provenance']['capture_index']):r for r in controls}
epoch=controls[0]['provenance']['reference_time_ms']-round(controls[0]['provenance']['send_time_s']*1000)
frame_by_time={epoch+round(t['sumo_time_s']*1000):f for f,t in timings.items()}
linked=[]
for anomaly in load(native/'anomalies.json'):
    row=by_key[(anomaly['receiver'],anomaly['capture_index'])]; c=row['control']; ident=anomaly['id']; frame=anomaly['frame_id']
    h=next(o for o in c['history'] if o['id']==ident); prev=frame_by_time[h['previous_measurement_time_ms']]
    d=diagnostics[(frame,ident)]; prior=diagnostics[(prev,ident)]; q=d['quality']
    sid={14:'hero1',15:'hero2'}[d['actor_id']]
    segment=[diagnostics[(f,ident)] for f in sorted(frames) if prev<f<=frame]
    updates=[s for s in segment if s['quality']['current_update'] is not None]
    largest=max(updates,key=lambda s:norm(s['quality']['current_update']['position_correction_world_m'])) if updates else None
    reference=poses[(frame,sid)]; old_reference=poses[(prev,sid)]
    linked.append({**anomaly,'station':c['station'],'previous_frame_id':prev,'actor_id':d['actor_id'],
        'source_sha256':row['provenance']['sha256'],'sumo_identity_inferred':sid,
        'identity_mapping_note':'geometric inference from calibration; not an archived identity dictionary',
        'current':d,'previous':prior,'maximum_correction_frame':None if largest is None else largest['frame_id'],
        'maximum_correction':None if largest is None else largest['quality']['current_update'],
        'interval_predictions':sum(s['quality']['phase']=='prediction_only' for s in segment),
        'simulated_reference_current':reference,'simulated_reference_previous':old_reference,
        'tracked_scalar_speed_world_m_s':norm([d['state_world']['vx'],d['state_world']['vy']]),
        'scalar_speed_difference_to_simulated_origin_m_s':norm([d['state_world']['vx'],d['state_world']['vy']])-reference['speed_m_s'],
        'simulated_scalar_acceleration_m_s2':(reference['speed_m_s']-old_reference['speed_m_s'])/anomaly['dt_s'],
        'causal_status':'numeric update/provenance demonstrated; centroid visibility cause and physical covariance unqualified',
        'original_fusion_file':str((a1/'fusion'/('frame-%d.json'%frame)).relative_to(root))})
assert len(linked)==24
(out/'exceedances-24.json').write_text(json.dumps(linked,indent=2,allow_nan=False))
flat=[]
for r in linked:
    q=r['current']['quality']; diag=q['model']['state_covariance_diagonal']
    flat.append({**{k:r[k] for k in ['receiver','station','frame_id','previous_frame_id','id','actor_id','check','dt_s','maximum_correction_frame','interval_predictions','scalar_speed_difference_to_simulated_origin_m_s','simulated_scalar_acceleration_m_s2']},
        'phase':q['phase'],'qualification':q['qualification'],'track_age_s':q['track_age_s'],'hits':q['hits'],'misses':q['misses'],
        'last_measurement_age_s':q['last_measurement_age_s'],'velocity_model_sigma_xy_m_s':q['model']['xy_velocity_model_sigma_m_s'],
        'model_position_variance_x':diag[0],'model_velocity_variance_x':diag[3],
        'last_model_nis':None if q['last_update'] is None else q['last_update']['normalized_innovation_squared_model']})
with (out/'exceedances-24.csv').open('w',newline='',encoding='utf-8') as f:
    writer=csv.DictWriter(f,fieldnames=list(flat[0])); writer.writeheader(); writer.writerows(flat)
(out/'tracker-diagnostics.json').write_text(json.dumps(list(diagnostics.values()),indent=2,allow_nan=False))
# Full-dropout counterexample, run on both actual implementations.
dropout={}
for name,mod in [('before',frozen),('after',current)]:
    detector=mod.FusionDetector.__new__(mod.FusionDetector); detector._trackers=[]; mod.KalmanTracker.count=0
    detector._update_trackers([dict(x=0.,y=0.,z=0.,score=1.,object_id=14,**{'class':'Car','class_id':1})],dt=.05)
    dropout[name]=[]
    for i in range(6):
        states=detector._update_trackers([],dt=.05)
        dropout[name].append({'empty_frame':i+1,'tracks':len(states),'misses':None if not states else states[0]['misses']})
(out/'dropout-counterexample.json').write_text(json.dumps(dropout,indent=2))
# Original emission fixtures plus optional metadata, same times/physical values.
replay=load(cal/'replay-index.json'); by_sha={r['sha256']:r for r in replay}; fixtures=[]
(out/'fixtures').mkdir()
for path in sorted((a1/'cpm-tx').glob('*.json')):
    trace=load(path); sha=hashlib.sha256(bytes.fromhex(trace['encoded_hex'])).hexdigest(); original=by_sha[sha]
    enriched=copy.deepcopy(trace['input']); frame=enriched['frame_id']
    for o in enriched['objects']:
        new_object=next(n for n in new_snapshots[frame]['objects'] if n['track_id']==o['track_id'])
        o.update(copy.deepcopy(new_object))
    filename=out/'fixtures'/('input-%02d.json'%original['capture_index']); filename.write_text(json.dumps(enriched,indent=2,allow_nan=False))
    fixtures.append({'input':'/repo/'+str(filename.relative_to(root)).replace('\\','/'),
        'expected':'/repo/results/phase3/'+pathlib.PurePosixPath(original['path']).relative_to('/evidence').as_posix(),
        'station':trace['station_id'],'reference_time_ms':trace['reference_time_ms'],'simulation_time_s':trace['simulation_time_s'],
        'frame_id':frame,'capture_index':original['capture_index'],'sha256':sha})
fixtures.sort(key=lambda e:e['capture_index']); assert len(fixtures)==38
(case/'fixture-index.json').write_text(json.dumps(fixtures,indent=2))
# Reuse the same original UPER bytes; receiver cannot infer producer quality.
for r in replay: r['path']='/repo/results/phase3/'+pathlib.PurePosixPath(r['path']).relative_to('/evidence').as_posix()
(case/'replay-index.json').write_text(json.dumps(replay,indent=2))
(case/'policy-selected.json').write_bytes((cal/'policy-selected.json').read_bytes())
phases=collections.Counter(d['quality']['phase'] for d in diagnostics.values())
model_sigmas=[d['quality']['model']['xy_velocity_model_sigma_m_s'] for d in diagnostics.values()]
summary={'passed':True,'frames':len(frames),'tracked_states':len(diagnostics),'max_state_difference_to_archive':float(max(errors)),
    'max_covariance_difference_to_before':float(max(covariance_errors)),'physical_contracts_identical':len(new_snapshots),
    'max_geographic_recompute_difference_to_archive':max(geographic_recompute_errors),
    'source_exceedances_joined':len(linked),'distinct_flagged_source_states':len({(r['frame_id'],r['id']) for r in linked}),
    'all_state_phases':dict(phases),'exceedance_phases':dict(collections.Counter(r['current']['quality']['phase'] for r in linked)),
    'state_qualifications':dict(collections.Counter(d['quality']['qualification'] for d in diagnostics.values())),
    'physical_covariance_calibrated':False,'model_sigma_xy_range_m_s':[min(model_sigmas),max(model_sigmas)],
    'numpy_version':np.__version__,'packet_fixtures':len(fixtures),
    'thresholds_changed':False,'f2md_quality_gating_enabled':False}
(out/'summary.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2))
