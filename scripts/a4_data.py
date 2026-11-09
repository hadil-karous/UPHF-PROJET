"""Read evidence only. ROS packet copies never contribute to native RX counters."""
import collections,csv,hashlib,json,pathlib
def load(path,default=None):
    if not path.exists():return default
    try:return json.loads(path.read_text(encoding='utf-8-sig'))
    except json.JSONDecodeError:return default
def lines(path):
    if not path.exists():return []
    text=path.read_text(encoding='utf-8-sig');records=[]
    for n,line in enumerate(text.splitlines()):
        try:records.append(json.loads(line))
        except json.JSONDecodeError:
            if n==len(text.splitlines())-1 and not text.endswith('\n'):break
            raise
    return records
def dataset(source,watch=False):
    source=pathlib.Path(source);case=source.parent if source.name.startswith('attempt-') else source
    attempt=source if source.name.startswith('attempt-') else next(iter(sorted(source.glob('attempt-*'),reverse=True)),source/'attempt-01')
    session=load(case/'session.json',{});is_live=watch and session.get('state')=='running' and not (attempt/'execution.json').exists()
    camera=lines(attempt/'camera-frames.jsonl')
    visual_states=lines(attempt/'visual-states.jsonl')
    traces=[]
    for f in sorted((attempt/'cpm-tx').glob('*.json')):
        t=load(f)
        if t:traces.append(t)
    bysha={hashlib.sha256(bytes.fromhex(t['encoded_hex'])).hexdigest():t for t in traces}
    native=[]
    for f in sorted((attempt/'f2md-events').glob('*.jsonl')):native.extend(lines(f))
    grouped=collections.defaultdict(list)
    for e in native:grouped[e['receiver'],e['event_id']].append(e)
    checks=[];counts=collections.Counter();timeline=[]
    for key,events in sorted(grouped.items()):
        decoded=next((e for e in events if e['stage']=='decode' and e['status']=='ok'),None)
        digest=hashlib.sha256(bytes.fromhex(decoded['source_r2_hex'])).hexdigest() if decoded else None
        trace=bysha.get(digest);frame=trace['input']['frame_id'] if trace else None
        for e in events:
            timeline.append({'time':e['simulation_time_s'],'stage':e['stage'],'status':e['status'],'receiver':e['receiver'],'frame_id':frame,'event_id':e['event_id']})
            if e['stage']=='control' and 'checks' in e:
                c=e['checks']
                for r in c['checks']:
                    counts[r['check'],r['status']]+=1
                    obj=next((o for o in trace['input']['objects'] if o['track_id']==r.get('id')),None) if trace else None
                    h=next((h for h in c['history'] if h['id']==r.get('id')),None)
                    checks.append({**r,'receiver':e['receiver'],'station':c['station'],'frame_id':frame,'time':e['simulation_time_s'],
                        'reference_time_ms':c['reference_time_ms'],'receive_time_ms':c['receive_time_ms'],
                        'source_object':obj,'history':h,'payload_sha256':digest})
    frames=[]
    for f in sorted((attempt/'fusion').glob('*.json')):
        e=load(f)
        if e:frames.append({'frame_id':e['frame_id'],'contract':e['contract'],'tracked_world':e['tracked_world']})
    frames.sort(key=lambda e:e['frame_id'])
    positions=[]
    if (attempt/'positions.csv').exists():
        with (attempt/'positions.csv').open() as f:positions=list(csv.DictReader(f))
    elif visual_states:
        positions=[{'sumo_id':v['sumo_id'],'carla_frame':s['frame_id'],'sumo_time':s['sumo_time_s'],**v} for s in visual_states for v in s['vehicles']]
    ros=lines(attempt/'ros-messages.jsonl');ros_cpm=sum(e['topic'].endswith('/cpm') for e in ros)
    report=load(attempt/'report.json',{});validation=load(attempt/'validation-a4.json')
    control_events=[e for e in native if e['stage']=='control' and 'checks' in e]
    metrics={'vehicles':len({r['sumo_id'] for r in positions}) if positions else None,'fusion_frames':len(frames),
        'cpm_tx':len(traces),'ros_cpm_copies':ros_cpm,'radio_rx':sum(e['stage']=='receive' for e in native),
        'decoded':sum(e['stage']=='decode' and e['status']=='ok' for e in native),'controlled':len(control_events),
        'conversion_rejections':sum(e['stage']=='convert' and e['status']!='ok' for e in native),
        'technical_errors':sum(e['status'] in ['technical_error','error'] for e in native),
        'non_evaluable_checks':sum(v for (k,s),v in counts.items() if s=='non_evaluable')}
    for t in traces:timeline.append({'time':t['simulation_time_s'],'stage':'CPM_TX','status':'encoded','frame_id':t['input']['frame_id'],'receiver':None})
    topics=report.get('topic_counts',{})
    components={'CARLA':{'evidence':len(frames),'unit':'instantanés Fusion issus du LiDAR'},
        'SUMO':{'evidence':len(positions),'unit':'positions de véhicules'},
        'ROS 2':{'evidence':sum(e['topic']=='/carla/hero/perceived_objects' for e in ros),'unit':'messages perception archivés'},
        'Artery':{'evidence':len(traces),'unit':'CPM encodés et émis'},
        'F2MD A3':{'evidence':len(control_events),'unit':'appels natifs de contrôle'}}
    return {'case':case.name,'attempt':attempt.name,'mode':'live' if is_live else 'replay',
        'session':session,'validated':bool(validation and validation.get('passed')),'metrics':metrics,
        'components':components,'checks':[{'check':k[0],'status':k[1],'count':v} for k,v in sorted(counts.items())],
        'objects':frames,'positions':positions,'object_checks':checks,'events':sorted(timeline,key=lambda e:e['time']),
        'camera_frames':[{**c,'url':'/video/'+c['view']+'/'+str(c['frame_id'])+'.png'} for c in camera],
        'visual_states':visual_states,
        'policy':validation.get('policy') if validation else None,
        'images':{name:'/evidence/'+name+'.png' for name in ['overview','onboard'] if (attempt/(name+'.png')).exists()},
        'topic_counts':topics,'limitations':'Centroïdes visibles ; estimations non calibrées. Dépassement ≠ attaque. Les contrôles restent partiels ; Kalman et distance/FoV désactivés.'}
