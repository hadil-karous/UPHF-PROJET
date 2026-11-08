"""Pure CARLA client Map conversion, NO server connection and NO ROS runtime.
The archived world/geo samples must match before any experimental CPM is built.
"""
import hashlib,json,os,pathlib
import carla
root=pathlib.Path('/repo'); case=pathlib.Path(os.environ['EXFMD_A34_CASE'])
a1=root/'results/phase1/a1-e2e-20261106-161848/attempt-02'; analysis=case/'analysis-validated'
map_path=root/'map-uphf/uphf_piste_aligned.xodr'
world_map=carla.Map('A34_offline',map_path.read_text())
def geo(x,y,z):
    g=world_map.transform_to_geolocation(carla.Location(x=x,y=y,z=z))
    return dict(latitude=g.latitude,longitude=g.longitude,altitude=g.altitude)
errors=[]
for path in (a1/'fusion').glob('frame-*.json'):
    f=json.loads(path.read_text()); points=[(f['reference_world'],f['reference_geo'])]
    for s,g,e in zip(f['tracked_world'],f['tracked_geo'],f['velocity_endpoint_geo']):
        points.extend([([s['x'],s['y'],s['z']],g),([s['x']+s['vx'],s['y']+s['vy'],s['z']+s['vz']],e)])
    for xyz,expected in points:
        actual=geo(*xyz); errors.append({k:abs(actual[k]-expected[k]) for k in actual})
maxima={k:max(e[k] for e in errors) for k in errors[0]}
valid=maxima['latitude']<1e-10 and maxima['longitude']<1e-10 and maxima['altitude']<1e-5
result={'offline_only':True,'map_source':str(map_path),'map_sha256':hashlib.sha256(map_path.read_bytes()).hexdigest(),
    'samples_checked':len(errors),'max_errors':maxima,'matches_archived_projection':valid}
(case/'offline-map-validation.json').write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2))
if not valid: raise SystemExit('Archived projection not reproduced; no experimental CPM coordinates will be invented')
converted={}
for variant in ['baseline','cwa_q2']:
    states=json.loads((analysis/(variant+'-states.json')).read_text()); rows=[]
    for state in states:
        p=geo(state['x'],state['y'],state['z']); e=geo(state['x']+state['vx'],state['y']+state['vy'],state['z']+state['vz'])
        rows.append({'frame_id':state['frame_id'],'track_id':state['track_id'],'position_geo':p,'endpoint_geo':e})
    converted[variant]=rows
(case/'experimental-geographic-points.json').write_text(json.dumps(converted,indent=2))
