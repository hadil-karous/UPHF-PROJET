"""Replay A1 payloads in measurement provenance order through actual CpmChecks.
Also compare every A2 speed decision against its immutable recorded baseline.
"""
import collections,csv,datetime,hashlib,json,os,pathlib,subprocess
root=pathlib.Path('/repo'); case=pathlib.Path(os.environ['EXFMD_A3_CASE']); build=case/'build'
assert json.loads((build/'test_a3.json').read_text())['passed']
out=case/'recorded'
if out.exists(): out=case/('recorded-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
out.mkdir(exist_ok=False)
core=root/'results/phase1/a1-e2e-20261106-161848/build'
env=dict(os.environ,LD_LIBRARY_PATH=str(build)+':'+str(core)+':/omnetpp/lib:'+os.environ.get('LD_LIBRARY_PATH',''))
baseline=root/'results/phase1/a2-20261106-170909'
old=json.loads((baseline/'recorded/summary.json').read_text())['results']
regression=[]
for entry in old:
    source=baseline/'recorded'/entry['corpus']/('input-%02d.uper'%entry['index'])
    result=out/('a2-%s-%02d.json'%(entry['corpus'],entry['index']))
    subprocess.run([str(build/'test_a2'),str(source),str(result)],env=env,check=True)
    now=json.loads(result.read_text())
    assert now['checks']==entry['control']['checks'] and now['result']==entry['control']['result']
    regression.append({'corpus':entry['corpus'],'index':entry['index'],'exact_control_match':True,
        'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
rows=list(csv.DictReader((root/'results/phase1/a1-e2e-20261106-161848/attempt-02/validation-01/object-comparisons.csv').open()))
by_index=collections.defaultdict(list)
for row in rows: by_index[int(row['capture_index'])].append(row)
replay=[]
for index,objects in sorted(by_index.items(),key=lambda pair:(int(pair[1][0]['reference_tai_ms']),pair[0])):
    row=objects[0]; source=baseline/'recorded/a1live'/('input-%02d.uper'%index)
    payload=source.read_bytes(); sha=hashlib.sha256(payload).hexdigest(); assert sha==row['payload_sha256']
    destination=out/('a1-%02d.uper'%index); destination.write_bytes(payload)
    replay.append({'path':str(destination),'sha256':sha,'capture_index':index,
        'frame_id':int(row['frame_id']),'object_ids':[int(o['track_id']) for o in objects],
        'measurement_carla_s':float(row['measurement_carla_s']),'measurement_sumo_s':float(row['measurement_sumo_s']),
        'send_time_s':float(row['emission_sumo_s']),'reference_time_ms':int(row['reference_tai_ms']),
        'receive_time_ms':int(row['reference_tai_ms']),'receiver':101,
        'source_csv':'results/phase1/a1-e2e-20261106-161848/attempt-02/validation-01/object-comparisons.csv'})
(case/'replay-index.json').write_text(json.dumps(replay,indent=2))
(out/'replay-index.json').write_text(json.dumps(replay,indent=2))
subprocess.run([str(build/'test_a3'),str(case/'replay-index.json'),str(out/'a3-controls.json')],env=env,check=True)
controls=json.loads((out/'a3-controls.json').read_text())
counts=collections.Counter(); reasons=collections.Counter(); actions=collections.Counter(); speed_matches=0; intervals=[]
for entry,result in zip(replay,controls):
    control=result['control']; assert control['verdict']!='technical_error' and not control['complete']
    expected=old[38+entry['capture_index']]['control']['checks']['evaluated']
    actual=[r for r in control['checks'] if r['check']=='speed_plausibility' and r['status']!='non_evaluable']
    assert [(r['id'],r['result']) for r in actual]==[(r['id'],r['result']) for r in expected]
    speed_matches+=len(actual)
    for row in control['checks']:
        counts[(row['check'],row['status'])]+=1
        if row['status']!='passed': reasons[(row['check'],row['status'],row['reason'])]+=1
    for row in control['history']:
        actions[row['history_action']]+=1
        if 'dt_s' in row: intervals.append(row['dt_s'])
summary={'passed':True,'cpm_processed':len(controls),'source':'A1 live attempt-02, original payloads and CSV frame provenance',
    'object_observations':sum(len(c['control']['history']) for c in controls),
    'a2_regression':{'messages_exact':len(regression),'evaluated_speed_results_exact':sum(len(e['control']['checks']['evaluated']) for e in old)},
    'a3_speed_results_equal_a2':speed_matches,'technical_errors':0,
    'checks':[{'check':k[0],'status':k[1],'count':v} for k,v in sorted(counts.items())],
    'reasons':[{'check':k[0],'status':k[1],'reason':k[2],'count':v} for k,v in sorted(reasons.items())],
    'history_actions':dict(actions),'interval_range_s':[min(intervals),max(intervals)] if intervals else None}
(out/'a2-regression.json').write_text(json.dumps(regression,indent=2))
(out/'summary.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2))
assert len(controls)==38 and len(regression)==76 and speed_matches==74
(case/'recorded-latest.txt').write_text(out.name)
