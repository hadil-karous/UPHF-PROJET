"""Reproducible A3.4 comparison on fixed archived associations and references.

Origin residual is a proxy between DIFFERENT geometric points. Only synthetic
analytic trajectories supply a point-matched exact reference in this study.
"""
import argparse,collections,csv,hashlib,importlib,json,math,pathlib,sys,types
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'cosimulation')]
try: import carla
except ImportError: sys.modules['carla']=types.ModuleType('carla')
from carla_multi_agent.fusion_detector import KalmanTracker,FusionDetector
from experiments.tracker_a34 import ExperimentalTracker,SETTINGS


def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def xy(o): return np.array([o['x'],o['y']],dtype=float)
def speed(o): return np.array([o['vx'],o['vy']],dtype=float)
def angle(a,b):
    # Shared reference mask; do not drop a bad estimate merely for low speed.
    if np.linalg.norm(a)<1e-9 or np.linalg.norm(b)<.2: return None
    return abs(math.degrees(math.remainder(math.atan2(a[1],a[0])-math.atan2(b[1],b[0]),2*math.pi)))
def stats(values):
    a=np.asarray([v for v in values if v is not None],dtype=float)
    if not len(a): return {'count':0}
    return {'count':len(a),'mean':float(a.mean()),'rmse':float(np.sqrt(np.mean(a*a))),
        'median':float(np.median(a)),'p95':float(np.percentile(a,95)),'maximum':float(a.max())}
def metrics(rows):
    result={'count':len(rows)}
    for name in ['origin_residual_m','centroid_residual_m','speed_scalar_residual_m_s','reference_vector_residual_m_s',
                 'direction_residual_deg','position_correction_m','innovation_m']:
        result[name]=stats([r.get(name) for r in rows])
    result['origin_bias_xy_m']=np.mean([r['origin_residual_xy_m'] for r in rows],axis=0).tolist() if rows else None
    return result


def reference_velocities(poses,frames):
    result={}
    for sid in ['hero1','hero2']:
        ids=sorted(f for f,s in poses if s==sid)
        for i,f in enumerate(ids):
            lo=ids[max(0,i-1)]; hi=ids[min(len(ids)-1,i+1)]
            dt=poses[(hi,sid)]['sumo_time']-poses[(lo,sid)]['sumo_time']
            result[(f,sid)]=(xy(poses[(hi,sid)])-xy(poses[(lo,sid)]))/dt
    return result


def synthetic(settings,kind):
    rng=np.random.default_rng(3401 if kind=='straight' else 3402)
    tracker=None; t=0.; records=[]; inputs=[]
    for i in range(180):
        dt=[.025,.05,.075][i%3]; t+=dt
        if kind=='straight': point=np.array([2*t,-.4*t]); velocity=np.array([2.,-.4])
        else: point=np.array([8*math.cos(.2*t),8*math.sin(.2*t)]); velocity=np.array([-1.6*math.sin(.2*t),1.6*math.cos(.2*t)])
        measurement=point+rng.normal(0,.08,2); missed=i%11==0 or i in [31,32]
        inputs.append((dt,measurement,point,velocity,t,missed))
    for dt,z,p,v,t,missed in inputs:
        obs=dict(x=float(z[0]),y=float(z[1]),z=0.,score=1.,object_id=14,**{'class':'Car','class_id':1})
        if tracker is None: tracker=ExperimentalTracker(obs,settings)
        else:
            tracker.predict(dt)
            if missed: tracker.misses+=1
            else: tracker.update(obs)
        if t>=1.:
            q=tracker.get_state()['estimation_quality']; update=q['current_update']
            records.append({'time_s':t,'position_error_m':float(np.linalg.norm(tracker.x[:2]-p)),
                'velocity_error_m_s':float(np.linalg.norm(tracker.x[3:5]-v)),
                'direction_error_deg':angle(tracker.x[3:5],v),'predicted':missed,
                'innovation_m':None if update is None else float(np.linalg.norm(update['innovation_world_m'][:2]))})
    # Same normal trajectory followed by one grossly inconsistent observation.
    tracker.predict(.05); base=tracker.x[:2].copy(); tracker.update(dict(x=float(base[0]+20),y=float(base[1]),z=0.,score=1.,object_id=14,**{'class':'Car','class_id':1}))
    q=tracker.get_state()['estimation_quality']; jump=float(np.linalg.norm(q['current_update']['innovation_world_m'][:2]))
    normal_max=max(r['innovation_m'] or 0 for r in records)
    assert jump>10 and jump>10*normal_max
    return {'position_error_m':stats([r['position_error_m'] for r in records]),
        'velocity_error_m_s':stats([r['velocity_error_m_s'] for r in records]),
        'direction_error_deg':stats([r['direction_error_deg'] for r in records]),
        'normal_innovation_max_m':normal_max,'gross_jump_innovation_m':jump,
        'gross_jump_model_nis':q['current_update']['normalized_innovation_squared_model'],
        'inconsistent_case_distinguishable':True,'records':records}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--case',required=True); parser.add_argument('--label',default='analysis'); args=parser.parse_args()
    assert args.label.startswith('analysis') and '/' not in args.label and '\\' not in args.label
    case=ROOT/args.case; out=case/args.label; out.mkdir(exist_ok=False)
    a1=ROOT/'results/phase1/a1-e2e-20261106-161848/attempt-02'
    frame_paths=sorted((a1/'fusion').glob('frame-*.json')); frames={load(p)['frame_id']:load(p) for p in frame_paths}
    poses={}
    for r in csv.DictReader((a1/'positions.csv').open()):
        poses[(int(r['carla_frame']),r['sumo_id'])]={k:float(r[k]) for k in ['x','y','z','speed_m_s','sumo_time','sync_position_error_m']}
    reference=reference_velocities(poses,frames)
    offsets=collections.defaultdict(list)
    for frame,f in frames.items():
        for d in f['raw_detections_world']:
            for sid in ['hero1','hero2']: offsets[(d['object_id'],sid)].append(float(np.linalg.norm(xy(d)-xy(poses[(frame,sid)]))))
    mapping={actor:min((np.median(values),sid) for (a,sid),values in offsets.items() if a==actor)[1]
        for actor in {a for a,s in offsets}}
    inventory={'run':str(a1.relative_to(ROOT)),'frames':len(frames),'tracked_states':sum(len(f['tracked_world']) for f in frames.values()),
        'raw_centroids':sum(len(f['raw_detections_world']) for f in frames.values()),'pose_rows':len(poses),
        'track_to_carla_explicit':{str(o['track_id']):o['source_object_id'] for f in frames.values() for o in f['tracked_world']},
        'carla_to_sumo_explicit_archived':False,'carla_to_sumo_geometric_inference':mapping,
        'ply_header':(a1/'lidar.ply').read_text().split('end_header')[0].splitlines(),
        'ply_scope':'first saved frame of a separate ordinary ray_cast LiDAR, no saved frame/actor index; not semantic per-frame input',
        'carla_object_boxes_or_dimensions_archived':False,'sumo_vtype_configured_length_m':4.5,
        'ros_cloud_data_logged':False,'ros_cloud_note':'Recorder returns after counting PointCloud2 bytes; no cloud payload in JSONL',
        'available_pointcloud_files':[str(p.relative_to(ROOT)) for directory in ['results/phase1','results/phase3','results/integrated']
            for p in (ROOT/directory).rglob('*') if p.is_file() and p.suffix.lower() in ['.ply','.pcd','.npz','.npy']],
        'packet_binary_not_lidar':'results/phase1/cpm-first-geonet-btp.bin',
        'data_files':{str(p.relative_to(ROOT)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in frame_paths+[a1/'positions.csv',a1/'frame-times.jsonl',a1/'lidar.ply',a1/'hero.rou.xml']}}
    (out/'inventory.json').write_text(json.dumps(inventory,indent=2))
    all_states={}; all_rows={}; comparisons=[]; correction1210={}
    for setting in SETTINGS:
        KalmanTracker.count=0; trackers={}; states={}; rows=[]; last_time=None
        for frame,f in sorted(frames.items()):
            dt=f['measurement_time_s']-last_time if last_time is not None else .1; last_time=f['measurement_time_s']
            raw={d['object_id']:d for d in f['raw_detections_world']}
            for saved in f['tracked_world']:
                ident=saved['track_id']; actor=saved['source_object_id']; sid=mapping[actor]; observation=raw.get(actor)
                if ident not in trackers:
                    assert observation is not None
                    trackers[ident]=ExperimentalTracker(observation,setting)
                    assert trackers[ident].id==ident
                else:
                    trackers[ident].predict(dt)
                    if observation is not None: trackers[ident].update(observation)
                    else: trackers[ident].misses+=1
                tracker=trackers[ident]; state=tracker.get_state(); states[(frame,ident)]=state
                if setting.name=='baseline':
                    assert all(state[k]==saved[k] for k in ['x','y','z','vx','vy','vz','hits','misses','source_object_id']), (frame,ident)
                ref=poses[(frame,sid)]; delta=xy(state)-xy(ref); update=state['estimation_quality']['current_update']
                row={'frame_id':frame,'track_id':ident,'carla_actor_id':actor,'sumo_identity_inferred':sid,
                    'time_s':ref['sumo_time'],'track_age_s':state['estimation_quality']['track_age_s'],
                    'phase':state['estimation_quality']['phase'],'origin_residual_xy_m':delta.tolist(),
                    'origin_residual_m':float(np.linalg.norm(delta)),
                    'centroid_residual_m':None if observation is None else float(np.linalg.norm(xy(state)-xy(observation))),
                    'speed_scalar_residual_m_s':abs(float(np.linalg.norm(speed(state)))-ref['speed_m_s']) if state['hits']>1 else None,
                    'reference_vector_residual_m_s':float(np.linalg.norm(speed(state)-reference[(frame,sid)])) if state['hits']>1 else None,
                    'direction_residual_deg':angle(speed(state),reference[(frame,sid)]) if state['hits']>1 else None,
                    'position_correction_m':None if update is None else float(np.linalg.norm(update['position_correction_world_m'][:2])),
                    'innovation_m':None if update is None else float(np.linalg.norm(update['innovation_world_m'][:2]))}
                if observation is not None:
                    geometric=xy(observation)-xy(ref); filter_residual=xy(state)-xy(observation)
                    assert np.max(np.abs(delta-geometric-filter_residual))<1e-12
                    row['centroid_origin_offset_xy_m']=geometric.tolist(); row['filter_residual_xy_m']=filter_residual.tolist()
                rows.append(row)
                if frame==1210 and ident==1:
                    previous_raw=next((frames[p] for p in sorted(frames,reverse=True) if p<frame and any(d['object_id']==actor for d in frames[p]['raw_detections_world'])),None)
                    old_d=next(d for d in previous_raw['raw_detections_world'] if d['object_id']==actor)
                    old_pose=poses[(previous_raw['frame_id'],sid)]
                    correction1210[setting.name]={'state':state,'reference_origin':ref,'raw_centroid':observation,
                        'previous_raw_frame':previous_raw['frame_id'],'previous_raw_centroid':old_d,
                        'centroid_offset_change_xy_m':((xy(observation)-xy(ref))-(xy(old_d)-xy(old_pose))).tolist(),
                        'current_origin_residual_m':row['origin_residual_m']}
        all_states[setting.name]=states; all_rows[setting.name]=rows
        summary={'name':setting.name,'parameters':setting.__dict__,'all':metrics(rows),
            'by_actor':{str(i):metrics([r for r in rows if r['carla_actor_id']==i]) for i in mapping},
            'by_phase':{p:metrics([r for r in rows if r['phase']==p]) for p in ['initializing','measurement_updated','prediction_only']},
            'by_age':{name:metrics([r for r in rows if low<=r['track_age_s']<hi]) for name,low,hi in [('0-.5',0,.5),('.5-1.5',.5,1.5),('1.5+',1.5,math.inf)]},
            'early':metrics([r for r in rows if r['time_s']<1.9]),'late':metrics([r for r in rows if r['time_s']>=1.9])}
        comparisons.append(summary)
        (out/(setting.name+'-rows.json')).write_text(json.dumps(rows,indent=2))
        (out/(setting.name+'-states.json')).write_text(json.dumps([{'frame_id':f,**s} for (f,i),s in states.items()],indent=2))
    # Geometric offset changes can be measured only when the centroid exists.
    geometric={}
    for actor,sid in mapping.items():
        values=[r['centroid_origin_offset_xy_m'] for r in all_rows['baseline'] if r['carla_actor_id']==actor and 'centroid_origin_offset_xy_m' in r]
        a=np.array(values); geometric[str(actor)]={'count':len(a),'mean_xy_m':a.mean(axis=0).tolist(),
            'std_xy_m':a.std(axis=0).tolist(),'range_xy_m':np.ptp(a,axis=0).tolist()}
    (out/'centroid_geometry.json').write_text(json.dumps(geometric,indent=2))
    (out/'frame-1210.json').write_text(json.dumps(correction1210,indent=2))
    (out/'parameter-comparison.json').write_text(json.dumps(comparisons,indent=2))
    synthetic_results={s.name:{kind:synthetic(s,kind) for kind in ['straight','curve']} for s in SETTINGS if s.name in ['baseline','cwa_q2','cwa_q025','cwa_q16']}
    (out/'synthetic-comparison.json').write_text(json.dumps(synthetic_results,indent=2))
    selected=next(s for s in comparisons if s['name']=='cwa_q2'); baseline=comparisons[0]
    summary={'passed':True,'baseline_matches_archive_exactly':True,'settings_count':len(SETTINGS),
        'baseline':baseline,'predeclared_candidate':selected,'point_representation_changed':False,
        'production_tracker_changed':False,'f2md_changed':False,'association_schedule':'fixed explicit track->CARLA from archive; SUMO reference inferred only',
        'synthetic_cases_distinguishable':all(s['inconsistent_case_distinguishable'] for v in synthetic_results.values() for s in v.values()),
        'direction_metric_mask':'reference planar speed >=0.2m/s and nonzero estimated vector; no F2MD threshold changed'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    print('Baseline matches all 148 archived states; '+str(len(SETTINGS))+' parameter settings replayed.')
    for s in comparisons:
        m=s['all']; print(s['name'], 'origin_RMSE',round(m['origin_residual_m']['rmse'],4),'centroid_residual_RMSE',round(m['centroid_residual_m']['rmse'],4),
            'speed_RMSE',round(m['speed_scalar_residual_m_s']['rmse'],4),'direction_MAE',round(m['direction_residual_deg']['mean'],3))


if __name__=='__main__': main()
