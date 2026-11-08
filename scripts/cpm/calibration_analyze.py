"""Join every frozen A3 exceedance to A1 frame evidence; no simulation or edits.

Replays the real tracker from archived centroids. SUMO poses are an internal
simulation reference, never an independent physical ground truth.
"""
import argparse,collections,csv,hashlib,importlib,json,math,pathlib,sys,types
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(); parser.add_argument('--case',required=True); parser.add_argument('--label',default='analysis'); args=parser.parse_args()
assert args.label.startswith('analysis') and '/' not in args.label and '\\' not in args.label
case=ROOT/args.case; out=case/args.label; out.mkdir(exist_ok=False)
A1=ROOT/'results/phase1/a1-e2e-20261106-161848/attempt-02'
A3=ROOT/'results/phase3/a3-20261108-182931'
native=A3/'native-20261108-174221-383958'
def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def norm(v): return math.hypot(v[0],v[1])
def vector(o): return np.array([o['x'],o['y'],o['z']],dtype=float)
frames={load(p)['frame_id']:load(p) for p in (A1/'fusion').glob('*.json')}
timings={r['frame_id']:r for r in map(json.loads,(A1/'frame-times.jsonl').read_text().splitlines())}
poses={}
for r in csv.DictReader((A1/'positions.csv').open()):
    poses[(int(r['carla_frame']),r['sumo_id'])]={k:float(r[k]) for k in ['x','y','z','speed_m_s','sumo_time','sync_position_error_m']}
sys.path.insert(0,str(ROOT/'cosimulation')); sys.modules['carla']=types.ModuleType('carla')
module=importlib.import_module('carla_multi_agent.fusion_detector')
module.KalmanTracker.count=0
detector=module.FusionDetector.__new__(module.FusionDetector); detector._trackers=[]
diagnostics={}; tracker_errors=[]; intervals=[]; last_time=None
for frame,f in sorted(frames.items()):
    dt=f['measurement_time_s']-last_time if last_time is not None else .1
    if last_time is not None: intervals.append(dt)
    last_time=f['measurement_time_s']; before={t.id:t.get_state() for t in detector._trackers}
    states=detector._update_trackers(f['raw_detections_world'],dt=dt)
    for actual,saved in zip(states,f['tracked_world']):
        assert actual['track_id']==saved['track_id'] and actual['source_object_id']==saved['source_object_id']
        tracker_errors.extend(abs(actual[k]-saved[k]) for k in ['x','y','z','vx','vy','vz'])
        ident=saved['track_id']; previous=before.get(ident)
        raw=next((o for o in f['raw_detections_world'] if o['object_id']==saved['source_object_id']),None)
        predicted=None if previous is None else vector(previous)+np.array([previous[k] for k in ['vx','vy','vz']])*dt
        diagnostics[(frame,ident)]={'tracker_step_s':dt,'prediction_only':saved['misses']>0,
            'raw_present':raw is not None,'hits':saved['hits'],'misses':saved['misses'],
            'raw_detection':raw,'tracked_world':saved,
            'predicted_position_world':None if predicted is None else predicted.tolist(),
            'innovation_m':None if predicted is None or raw is None else (vector(raw)-predicted).tolist(),
            'position_update_correction_m':None if predicted is None else (vector(saved)-predicted).tolist(),
            'velocity_update_m_s':None if previous is None else [saved[k]-previous[k] for k in ['vx','vy','vz']]}
assert max(tracker_errors)<2e-5, max(tracker_errors)
# Geometric mapping only: actor/SUMO identity mapping itself was not archived.
distances=collections.defaultdict(list)
for frame,f in frames.items():
    for raw in f['raw_detections_world']:
        for sid in ['hero1','hero2']:
            if (frame,sid) in poses: distances[(raw['object_id'],sid)].append(norm(vector(raw)-vector(poses[(frame,sid)])))
mapping={}
for actor in {key[0] for key in distances}:
    options=sorted((float(np.median(v)),sid) for (a,sid),v in distances.items() if a==actor)
    mapping[actor]={'sumo_id':options[0][1],'method':'inferred minimum median centroid-to-pose distance; not archived explicit identity',
        'median_distance_m':options[0][0],'next_median_distance_m':options[1][0]}
rows=load(native/'offline-controls.json'); by_capture={(r['provenance']['receiver'],r['provenance']['capture_index']):r for r in rows}
epoch=rows[0]['provenance']['reference_time_ms']-round(rows[0]['provenance']['send_time_s']*1000)
frame_by_measurement={epoch+round(v['sumo_time_s']*1000):k for k,v in timings.items()}
joined=[]
for anomaly in load(native/'anomalies.json'):
    entry=by_capture[(anomaly['receiver'],anomaly['capture_index'])]
    control=entry['control']; ident=anomaly['id']; frame=anomaly['frame_id']
    state=next(s for s in control['history'] if s['id']==ident)
    previous_frame=frame_by_measurement[state['previous_measurement_time_ms']]
    current=diagnostics[(frame,ident)]; previous=diagnostics[(previous_frame,ident)]
    current_f=frames[frame]; previous_f=frames[previous_frame]
    actor=current['tracked_world']['source_object_id']; sid=mapping[actor]['sumo_id']
    a=poses[(previous_frame,sid)]; b=poses[(frame,sid)]; dt=state['dt_s']
    segment=[diagnostics[(f,ident)] for f in sorted(frames) if previous_frame<f<=frame]
    offset_change=None
    if previous['raw_detection'] and current['raw_detection']:
        offset_change=(vector(current['raw_detection'])-vector(b))-(vector(previous['raw_detection'])-vector(a))
        offset_change=offset_change.tolist()
    span_predictions=sum(s['prediction_only'] for s in segment)
    contract0=next(o for o in previous_f['contract']['objects'] if o['track_id']==ident)
    contract1=next(o for o in current_f['contract']['objects'] if o['track_id']==ident)
    unquantized_speed_delta=norm([contract1['vx'],contract1['vy']])-norm([contract0['vx'],contract0['vy']])
    heading_change=None
    if contract0['vx'] is not None and contract1['vx'] is not None:
        heading_change=abs(math.degrees(math.remainder(math.atan2(contract1['vy'],contract1['vx'])-math.atan2(contract0['vy'],contract0['vx']),2*math.pi)))
    tracked_displacement=norm(vector(current['tracked_world'])-vector(previous['tracked_world']))
    ref_displacement=norm(vector(b)-vector(a))
    reference_turn=None
    if (previous_frame-1,sid) in poses and (frame-1,sid) in poses:
        va=vector(a)-vector(poses[(previous_frame-1,sid)]); vb=vector(b)-vector(poses[(frame-1,sid)])
        if norm(va)>1e-5 and norm(vb)>1e-5:
            reference_turn=abs(math.degrees(math.remainder(math.atan2(vb[1],vb[0])-math.atan2(va[1],va[0]),2*math.pi)))
    current_reference=poses[(frame,'hero')]; old_reference=poses[(previous_frame,'hero')]
    geo_rotation=math.degrees(math.atan2(current_f['sensor_transform'][1][0],current_f['sensor_transform'][0][0])-math.atan2(previous_f['sensor_transform'][1][0],previous_f['sensor_transform'][0][0]))
    notes=['tracker replay reproduces saved state','source threshold exceeded; not proof of an attack']
    if span_predictions: notes.append('prediction-only states present in comparison interval')
    if offset_change is not None and norm(offset_change)>.05: notes.append('archived centroid offset relative to simulated actor varies >5cm')
    if any(norm(s['position_update_correction_m'] or [0,0])>.1 for s in segment): notes.append('Kalman measurement update corrects position >10cm in interval')
    if anomaly['check']=='speed_consistency' and abs(b['speed_m_s']-a['speed_m_s'])<=control['policy']['acceleration_m_s2']*dt+.015:
        notes.append('simulated actor scalar-speed change within configured threshold, unlike tracked estimate')
    rounded_only=False
    if anomaly['check']=='speed_consistency': rounded_only=abs(unquantized_speed_delta)<=anomaly['allowed_change_m_s']
    elif anomaly['check']=='direction_consistency': rounded_only=heading_change<=anomaly['allowed_change_deg']
    else: rounded_only=tracked_displacement<=anomaly['allowed_distance_m']
    joined.append({**anomaly,'station':control['station'],'source_sha256':entry['provenance']['sha256'],
        'previous_frame_id':previous_frame,'previous_measurement_time_ms':state['previous_measurement_time_ms'],
        'carla_time_s':current_f['measurement_time_s'],'sumo_time_s':timings[frame]['sumo_time_s'],
        'actor_id':actor,'sumo_mapping':mapping[actor],'policy':control['policy'],
        'current':current,'previous':previous,'interval_predictions':span_predictions,'interval_sensor_states':len(segment),
        'maximum_update_correction_m':max(norm(s['position_update_correction_m'] or [0,0]) for s in segment),
        'centroid_offset_change_world_m':offset_change,'simulated_pose_current':b,'simulated_pose_previous':a,
        'reference_displacement_m':ref_displacement,'tracked_world_displacement_m':tracked_displacement,
        'simulated_scalar_acceleration_m_s2':(b['speed_m_s']-a['speed_m_s'])/dt,
        'simulated_direction_change_deg':reference_turn,'unquantized_metric_below_original_bound':rounded_only,
        'unquantized_speed_change_m_s':unquantized_speed_delta,'unquantized_direction_change_deg':heading_change,
        'sensor_yaw_change_deg':geo_rotation,'notes':notes,
        'cause_status':'estimator effects measured; no proof of attack or independent physical false positive',
        'unresolved':['visibility/occlusion cause of centroid variation','calibrated sensor/velocity covariance','independent physical ground truth'],
        'source_files':{'fusion_current':str((A1/'fusion'/('frame-%d.json'%frame)).relative_to(ROOT)),
            'fusion_previous':str((A1/'fusion'/('frame-%d.json'%previous_frame)).relative_to(ROOT)),
            'simulation_reference':str((A1/'positions.csv').relative_to(ROOT))}})
assert len(joined)==40
(out/'exceedances-linked.json').write_text(json.dumps(joined,indent=2),encoding='utf-8')
flat=[]
for r in joined:
    flat.append({**{k:r[k] for k in ['receiver','station','id','actor_id','frame_id','previous_frame_id','capture_index','check','dt_s','interval_predictions','maximum_update_correction_m','reference_displacement_m','tracked_world_displacement_m','simulated_scalar_acceleration_m_s2','simulated_direction_change_deg','unquantized_metric_below_original_bound','unquantized_speed_change_m_s','unquantized_direction_change_deg','sensor_yaw_change_deg','source_sha256','cause_status']},'evidence_notes':'; '.join(r['notes'])})
with (out/'exceedances-linked.csv').open('w',newline='',encoding='utf-8') as f:
    writer=csv.DictWriter(f,fieldnames=list(flat[0])); writer.writeheader(); writer.writerows(flat)
(out/'tracker-diagnostics.json').write_text(json.dumps([{'frame_id':k[0],'track_id':k[1],**v} for k,v in diagnostics.items()],indent=2))
summary={'observations':len(joined),'unique_source_comparisons':len({(r['capture_index'],r['id'],r['check']) for r in joined}),
    'unique_frame_track_checks':len({(r['frame_id'],r['id'],r['check']) for r in joined}),
    'tracker_replay_max_component_error':max(tracker_errors),'sensor_step_s_range':[min(intervals),max(intervals)],
    'geometric_identity_mapping':mapping,'with_prediction_in_interval':sum(r['interval_predictions']>0 for r in joined),
    'with_position_update_over_10cm':sum(r['maximum_update_correction_m']>.1 for r in joined),
    'maximum_sensor_yaw_change_deg':max(abs(r['sensor_yaw_change_deg']) for r in joined),
    'maximum_reference_direction_change_deg':max(r['simulated_direction_change_deg'] or 0 for r in joined),
    'unquantized_metric_below_original_bound':sum(r['unquantized_metric_below_original_bound'] for r in joined),
    'counts':dict(collections.Counter(r['check'] for r in joined))}
(out/'summary.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2))
