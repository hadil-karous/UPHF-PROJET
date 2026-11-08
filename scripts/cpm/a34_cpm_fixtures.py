"""Build isolated CPM input fixtures from actual offline CARLA map projections."""
import argparse,copy,hashlib,json,pathlib,sys,types
root=pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0,str(root/'cosimulation'))
from carla_multi_agent.perception_contract import enu
parser=argparse.ArgumentParser(); parser.add_argument('--case',required=True); args=parser.parse_args()
case=root/args.case; analysis=case/'analysis-validated'; out=case/'cpm-inputs'; out.mkdir(exist_ok=False)
def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
assert load(case/'offline-map-validation.json')['matches_archived_projection']
geos=load(case/'experimental-geographic-points.json')
states={name:{(s['frame_id'],s['track_id']):s for s in load(analysis/(name+'-states.json'))} for name in ['baseline','cwa_q2']}
points={name:{(g['frame_id'],g['track_id']):g for g in rows} for name,rows in geos.items()}
a1=root/'results/phase1/a1-e2e-20261106-161848/attempt-02'
replay=load(root/'results/phase3/calibration-20261108-190113/replay-index.json'); bysha={r['sha256']:r for r in replay}; index=[]
for path in (a1/'cpm-tx').glob('*.json'):
    trace=load(path); sha=hashlib.sha256(bytes.fromhex(trace['encoded_hex'])).hexdigest(); source=bysha[sha]; frame=trace['input']['frame_id']
    f=load(a1/'fusion'/('frame-%d.json'%frame)); ref=types.SimpleNamespace(**f['reference_geo'])
    entry={'capture_index':source['capture_index'],'frame_id':frame,'source_sha256':sha,'station':trace['station_id'],
        'reference_time_ms':trace['reference_time_ms'],'simulation_time_s':trace['simulation_time_s'],
        'expected':'/repo/results/phase3/'+pathlib.PurePosixPath(source['path']).relative_to('/evidence').as_posix()}
    for name in ['baseline','cwa_q2']:
        data=copy.deepcopy(trace['input'])
        for obj in data['objects']:
            state=states[name][(frame,obj['track_id'])]; g=points[name][(frame,obj['track_id'])]
            p=enu(types.SimpleNamespace(**g['position_geo']),ref); e=enu(types.SimpleNamespace(**g['endpoint_geo']),ref)
            obj.update(zip(['x','y','z'],p)); obj['vx']=obj['vy']=None
            if state['hits']>1: obj['vx']=e[0]-p[0]; obj['vy']=e[1]-p[1]
            obj['estimation_quality']=state['estimation_quality']
        output=out/(name+'-%02d.json'%source['capture_index']); output.write_text(json.dumps(data,indent=2,allow_nan=False))
        entry[name]='/repo/'+output.relative_to(root).as_posix()
    index.append(entry)
index.sort(key=lambda r:r['capture_index']); assert len(index)==38
(case/'cpm-index.json').write_text(json.dumps(index,indent=2)); print('38 paired baseline/candidate CPM fixtures prepared; no historical capture changed')
