"""Re-evaluate each native receiver sequence using its actual clock/parameters.
This calls the newly linked CpmChecks, then compares every structured decision.
"""
import collections,hashlib,json,os,pathlib,subprocess
case=pathlib.Path(os.environ['EXFMD_A3_CASE'])
build=pathlib.Path(os.environ.get('EXFMD_A3_REPLAY_BUILD',str(case/'build')))
native=max(p for p in case.glob('native-*') if p.is_dir())
assert json.loads((native/'result.json').read_text())['exit_code']==0
env=dict(os.environ,LD_LIBRARY_PATH=str(build)+':/repo/results/phase1/a1-e2e-20261106-161848/build:/omnetpp/lib:'+os.environ.get('LD_LIBRARY_PATH',''))
inputs=json.loads((case/'replay-index.json').read_text()); bysha={e['sha256']:e for e in inputs}
groups=collections.defaultdict(list)
for file in (native/'events').glob('*.jsonl'):
    for line in file.read_text().splitlines():
        e=json.loads(line); groups[(e['receiver'],e['event_id'])].append(e)
entries=[]; originals=[]
for (receiver,event),events in sorted(groups.items()):
    assert [e['stage'] for e in events]==['receive','decode','convert','control','non_evaluable']
    source=bysha[hashlib.sha256(bytes.fromhex(events[1]['source_r2_hex'])).hexdigest()]
    controlled=events[3]
    assert controlled['facility_called'] and controlled['temporal_checks_called'] and not controlled['checks']['complete']
    entries.append({**source,'receiver':receiver,'receive_time_ms':controlled['checks']['receive_time_ms'],'parameters':controlled['checks']['policy']})
    originals.append(controlled['checks'])
(native/'offline-index.json').write_text(json.dumps(entries,indent=2))
subprocess.run([str(build/'test_a3'),str(native/'offline-index.json'),str(native/'offline-controls.json')],check=True,env=env)
actual=json.loads((native/'offline-controls.json').read_text())
for a,b in zip(actual,originals): assert a['control']==b, 'native/offline actual CpmChecks decision mismatch'
assert len(actual)==76
receiver_payloads=collections.Counter((e['receiver'],e['sha256']) for e in entries)
assert len(receiver_payloads)==76 and all(v==1 for v in receiver_payloads.values())
accepted={}; history_steps=0; anomalies=[]; compared=[]
epoch=inputs[0]['reference_time_ms']-round(inputs[0]['send_time_s']*1000)
for entry,control in zip(entries,originals):
    assert control['reference_time_ms']==entry['reference_time_ms']
    assert control['reference_time_ms']<=control['receive_time_ms']
    for expiry in control['expired']: accepted.pop((entry['receiver'],expiry['station'],expiry['id']),None)
    for state in control['history']:
        key=(entry['receiver'],control['station'],state['id'])
        assert state['id'] in entry['object_ids']
        assert state['measurement_time_ms']==epoch+round(entry['measurement_sumo_s']*1000)
        if 'dt_s' in state:
            previous=accepted[key]
            assert state['previous_measurement_time_ms']==previous
            assert state['dt_ms']==state['measurement_time_ms']-previous
            assert state['dt_s']==(state['measurement_time_ms']-previous)/1000.
        per_object=[r for r in control['checks'] if r.get('id')==state['id']]
        object_anomalies=[r for r in per_object if r['status']=='anomaly']
        if state['history_action'] in ['initialized','updated']:
            assert not object_anomalies
            assert any(r['check']=='temporal_order' and r['status']=='passed' for r in per_object)
            accepted[key]=state['measurement_time_ms']
        else:
            assert state['history_action']=='rejected'
        for row in object_anomalies:
            anomalies.append({'receiver':entry['receiver'],'frame_id':entry['frame_id'],'capture_index':entry['capture_index'],**row})
        compared.append({'receiver':entry['receiver'],'station':control['station'],'frame_id':entry['frame_id'],
            'source_sha256':entry['sha256'],**state})
        history_steps+=1
(native/'history-comparisons.json').write_text(json.dumps(compared,indent=2))
(native/'anomalies.json').write_text(json.dumps(anomalies,indent=2))
baseline=pathlib.Path('/repo/results/phase1/a2-20261106-170909/native-20261106-162435-077753')
oldgroups=collections.defaultdict(list)
for file in (baseline/'events').glob('*.jsonl'):
    for line in file.read_text().splitlines():
        e=json.loads(line); oldgroups[(e['receiver'],e['event_id'])].append(e)
native_by_sha=collections.defaultdict(list)
for entry,control in zip(entries,originals):
    values=[(r['id'],r['result']) for r in control['checks'] if r['check']=='speed_plausibility' and r['status']!='non_evaluable']
    native_by_sha[entry['sha256']].append(values)
previous_receptions=previous_speed_checks=0
for events in oldgroups.values():
    decoded=next(e for e in events if e['stage']=='decode')
    controlled=next(e for e in events if e['stage']=='control')
    values=[(r['id'],r['result']) for r in controlled['checks']['evaluated'] if r['check']=='speed_plausibility']
    sha=hashlib.sha256(bytes.fromhex(decoded['source_r2_hex'])).hexdigest()
    assert sha in native_by_sha and all(v==values for v in native_by_sha[sha])
    previous_receptions+=1; previous_speed_checks+=len(values)
assert previous_receptions==20 and previous_speed_checks==36
result={'passed':True,'exact_control_comparisons':len(actual),'exact_payloads_and_provenance':len(actual),
    'independent_source_frame_and_history_checks':history_steps,'anomaly_observations':len(anomalies),
    'previous_a2_native_receptions_compared':previous_receptions,'previous_a2_native_speed_checks_identical':previous_speed_checks,
    'receivers':sorted({e['receiver'] for e in entries}),
    'speed_limit_by_receiver':{str(e['receiver']):e['parameters']['speed_limit_m_s'] for e in entries}}
(native/'verification.json').write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2))
