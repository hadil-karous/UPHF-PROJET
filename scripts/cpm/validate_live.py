"""Decode real captured CPMs and compare exact bytes/frame/ID with live evidence.
Does not launch a simulation. No nearest-time or nearest-position pairing of CPMs.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(); parser.add_argument('--attempt',required=True)
args=parser.parse_args(); attempt=Path(args.attempt).resolve()
relative=attempt.relative_to(ROOT)
out=next(attempt/('validation-%02d'%i) for i in range(1,100) if not (attempt/('validation-%02d'%i)).exists())
out.mkdir(exist_ok=False)
def load(path): return json.loads(path.read_text(encoding='utf-8-sig'))
errors=[]
def require(ok,label):
    if not ok: errors.append(label)
def close(a,b,tolerance,label):
    error=abs(a-b); require(error<=tolerance,label+': '+str(error)); return error
def rounded(v): return math.floor(v+.5) if v>=0 else math.ceil(v-.5)
def sha(b): return hashlib.sha256(b).hexdigest()
times={r['frame_id']:r for r in (json.loads(l) for l in (attempt/'frame-times.jsonl').read_text().splitlines())}
perceptions={}; packets=[]
for line_no,line in enumerate((attempt/'ros-messages.jsonl').read_text().splitlines(),1):
    record=json.loads(line)
    if record['topic']=='/carla/hero/perceived_objects':
        data=json.loads(record['message']['data']); frame=data['frame_id']
        if frame in perceptions: require(data==perceptions[frame],'conflicting ROS frame '+str(frame))
        perceptions[frame]=data
    elif record['topic'].endswith('/cpm'):
        packet=bytes.fromhex(record['message']['hex'])
        require(len(packet)==record['message']['bytes'],'packet length')
        require(int.from_bytes(packet[40:42],'big')==2009,'BTP port')
        packets.append({'packet':packet,'line':line_no,'topic':record['topic']})
joined={load(p)['frame_id']:load(p) for p in (attempt/'joined-perceptions').glob('*.json')}
fusion={load(p)['frame_id']:load(p) for p in (attempt/'fusion').glob('*.json')}
traces={}
for path in (attempt/'cpm-tx').glob('*.json'):
    trace=load(path); trace['evidence_file']=path.name
    digest=sha(bytes.fromhex(trace['encoded_hex']))
    require(digest not in traces,'duplicate encoded trace')
    traces[digest]=trace
require(bool(packets),'no CPM packets'); require(bool(traces),'no CPM emission traces')
rows=[]; used=set(); position_errors=[]; velocity_errors=[]; ages=[]; time_errors=[]; first_example=None
for index,item in enumerate(packets):
    payload=item['packet'][44:]; digest=sha(payload)
    require(digest in traces,'captured packet missing exact emission trace')
    if digest not in traces: continue
    used.add(digest); trace=traces[digest]; data=trace['input']; frame=data['frame_id']
    require(frame in times and frame in perceptions and frame in joined and frame in fusion,'missing chain frame '+str(frame))
    if frame not in times or frame not in perceptions or frame not in joined or frame not in fusion: continue
    require(data==joined[frame],'emitted snapshot differs from archived joined frame')
    require(fusion[frame]['contract']==perceptions[frame],'Fusion/ROS content differs')
    restored=dict(data); restored['time_base']='carla_simulation_seconds'
    restored['measurement_time_s']=restored.pop('carla_measurement_time_s')
    require(restored==perceptions[frame],'ROS/join changed fields beyond clock conversion')
    time_errors.append(close(data['measurement_time_s'],times[frame]['sumo_time_s'],1e-9,'SUMO frame join'))
    time_errors.append(close(data['carla_measurement_time_s'],times[frame]['carla_time_s'],1e-6,'CARLA sensor/frame time'))
    path=out/('packet-%03d.uper'%index); path.write_bytes(payload)
    linux='/repo/'+(path.relative_to(ROOT)).as_posix()
    result=subprocess.run(['docker','exec','exfmd-cpm-a1','/evidence/decode_cpm','r2',linux],capture_output=True,text=True)
    if result.returncode:
        errors.append('ASN.1 decode failure '+str(index)); continue
    decoded=json.loads(result.stdout)
    (out/('packet-%03d.json'%index)).write_text(json.dumps(decoded,indent=2),encoding='utf-8')
    require(decoded['decoded'] and decoded['valid'] and decoded['consumed_bytes']==len(payload),'R2 constraints/consumption')
    require(decoded['station_id']==trace['station_id'],'station ID')
    require(decoded['reference_time_ms']==trace['reference_time_ms'],'TAI reference')
    expected_delta=rounded((data['measurement_time_s']-trace['simulation_time_s'])*1000)
    require(-2048<=expected_delta<=0,'invalid measurement age')
    ages.append(-expected_delta)
    require({o['id'] for o in decoded['objects']}=={o['track_id'] for o in data['objects']},'object IDs')
    require(len(decoded['objects'])==len(data['objects']),'object count')
    for key in ['latitude','longitude']:
        close(decoded['reference'][key],data['reference'][key],.500001e-7,'geographical reference rounding')
    for source in data['objects']:
        matches=[o for o in decoded['objects'] if o['id']==source['track_id']]
        if len(matches)!=1: errors.append('missing/duplicate decoded ID'); continue
        obj=matches[0]
        require(obj['measurement_delta_ms']==expected_delta,'signed measurement delta')
        row={'capture_index':index,'jsonl_line':item['line'],'frame_id':frame,'track_id':source['track_id'],
            'station_id':decoded['station_id'],'payload_sha256':digest,'measurement_sumo_s':data['measurement_time_s'],
            'measurement_carla_s':data['carla_measurement_time_s'],'emission_sumo_s':trace['simulation_time_s'],
            'reference_tai_ms':decoded['reference_time_ms'],'measurement_delta_ms':obj['measurement_delta_ms']}
        for axis in ['x','y','z']:
            key=axis+'_m'
            error=close(source[axis],obj[key],.005000001,'position '+axis)
            position_errors.append(error); row['source_'+axis+'_m']=source[axis]; row['decoded_'+axis+'_m']=obj[key]
        for axis in ['vx','vy']:
            key=axis+'_m_s'; value=source.get(axis)
            if value is None:
                require(key not in obj,'unknown velocity fabricated'); row['source_'+key]=None; row['decoded_'+key]=None
            else:
                require(key in obj,'velocity missing')
                if key in obj:
                    error=close(value,obj[key],.005000001,'velocity '+axis)
                    velocity_errors.append(error); row['source_'+key]=value; row['decoded_'+key]=obj[key]
        require(not obj['acceleration_present'] and not obj['length_present'] and not obj['width_present'] and not obj['sensor_ids_present'],'unavailable data fabricated')
        if source['class']=='Car': require(obj.get('vehicle_class')==5,'Car classification')
        rows.append(row)
        if first_example is None and source.get('vx') is not None and abs(source['vx'])>.01:
            first_example=row
# Check map-derived ENU independently from the saved geodetic intermediate values.
def xyz(g):
    lat=math.radians(g['latitude']); lon=math.radians(g['longitude']); h=g['altitude']
    n=6378137./math.sqrt(1-6.69437999014e-3*math.sin(lat)**2)
    return ((n+h)*math.cos(lat)*math.cos(lon),(n+h)*math.cos(lat)*math.sin(lon),(n*(1-6.69437999014e-3)+h)*math.sin(lat))
def enu(g,ref):
    delta=[a-b for a,b in zip(xyz(g),xyz(ref))]
    p=math.radians(ref['latitude']); l=math.radians(ref['longitude'])
    basis=((-math.sin(l),math.cos(l),0),(-math.sin(p)*math.cos(l),-math.sin(p)*math.sin(l),math.cos(p)),(math.cos(p)*math.cos(l),math.cos(p)*math.sin(l),math.sin(p)))
    return [sum(x*y for x,y in zip(axis,delta)) for axis in basis]
source_ids={}; geometric_errors=[]; enu_velocity_errors=[]; duplicate_source_matches=0; predicted_states=0
for frame,evidence in sorted(fusion.items()):
    contract=evidence['contract']; world=evidence['tracked_world']; reference=evidence['reference_geo']
    associations=set()
    for k,state in enumerate(world):
        source=contract['objects'][k]
        values=enu(evidence['tracked_geo'][k],reference)
        for i,axis in enumerate(['x','y','z']):
            geometric_errors.append(close(values[i],source[axis],1e-7,'ENU recomputation'))
        if state['hits']>1:
            endpoint=enu(evidence['velocity_endpoint_geo'][k],reference)
            for i,axis in enumerate(['vx','vy']):
                enu_velocity_errors.append(close(endpoint[i]-values[i],source[axis],1e-7,'ground ENU velocity recomputation'))
        else: require(source['vx'] is None and source['vy'] is None,'first-hit velocity fabricated')
        source_id=state.get('source_object_id')
        require(source_id is not None,'actual source assignment not recorded')
        source_ids.setdefault(state['track_id'],set()).add(source_id)
        if state.get('misses',0)>0:
            predicted_states+=1
        else:
            raw_ids={o['object_id'] for o in evidence['raw_detections_world']}
            require(source_id in raw_ids,'updated track has no source detection')
            if source_id in associations: duplicate_source_matches+=1
            associations.add(source_id)
require(all(len(ids)==1 for ids in source_ids.values()),'track switches source actor')
require(duplicate_source_matches==0,'two tracks associate to same detected actor')
require(used==set(traces),'some emitted CPM traces absent from ROS captures')
execution=load(attempt/'execution.json'); require(execution['ros_exit_code']==0 and execution['artery_exit_code']==0,'scenario exit')
memory=(attempt/'artery-memory-maps.txt').read_text()
require('libartery_F2MD' not in memory,'F2MD library loaded')
summary={'passed':not errors,'errors':errors,'captured_cpm':len(packets),'emission_traces':len(traces),
    'matched_payloads':len(used),'compared_object_rows':len(rows),'unique_emitted_frames':len(set(r['frame_id'] for r in rows)),
    'ros_perception_frames':len(perceptions),'joined_frames':len(joined),'fusion_frames':len(fusion),'registered_frames':len(times),
    'track_source_actor_ids':{str(k):sorted(v) for k,v in source_ids.items()},
    'predicted_track_states':predicted_states,
    'max_position_quantization_error_m':max(position_errors,default=None),
    'max_velocity_quantization_error_m_s':max(velocity_errors,default=None),
    'max_frame_join_error_s':max(time_errors,default=None),'measurement_age_ms':[min(ages),max(ages)] if ages else None,
    'max_enu_recomputation_error_m':max(geometric_errors,default=None),
    'max_enu_velocity_recomputation_error_m_s':max(enu_velocity_errors,default=None),
    'example':first_example,'execution':execution}
(out/'validation.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
if rows:
    with (out/'object-comparisons.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
print(json.dumps({'output':str(out),**summary},indent=2))
raise SystemExit(0 if summary['passed'] else 1)
