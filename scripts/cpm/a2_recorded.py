"""Inside the isolated image: replay existing R2 bytes through conversion and
the actual linked F2MD CpmChecks, without running a simulation."""
import json,os,pathlib,subprocess,hashlib
case=pathlib.Path(os.environ['EXFMD_A2_CASE']); out=case/'recorded'; out.mkdir(exist_ok=False)
env=dict(os.environ,LD_LIBRARY_PATH=str(case/'build')+':/repo/results/phase1/a1-e2e-20261106-161848/build:/omnetpp/lib:'+os.environ.get('LD_LIBRARY_PATH',''))
inputs=[('nov05',pathlib.Path('/repo/results/integrated/run-20261105-151425/ros-messages.jsonl')),
        ('a1live',pathlib.Path('/repo/results/phase1/a1-e2e-20261106-161848/attempt-02/ros-messages.jsonl'))]
results=[]; replay=[]
for label,path in inputs:
    destination=out/label; destination.mkdir()
    records=[json.loads(line) for line in path.open()]
    for i,record in enumerate(r for r in records if r['topic'].endswith('/cpm')):
        data=bytes.fromhex(record['message']['hex'])[44:]; source=destination/('input-%02d.uper'%i); source.write_bytes(data)
        prefix=destination/('converted-%02d'%i)
        result=subprocess.run([str(case/'build/a2_convert'),str(source),str(prefix)],capture_output=True,text=True,env=env)
        (destination/('conversion-%02d.log'%i)).write_text(result.stdout+result.stderr)
        if result.returncode: raise RuntimeError('recorded conversion failed: '+str(source))
        convert=json.loads(prefix.with_suffix('.json').read_text())
        control=destination/('control-%02d.json'%i)
        subprocess.run([str(case/'build/test_a2'),str(source),str(control)],check=True,env=env)
        checks=json.loads(control.read_text())
        decoded=subprocess.run(['/evidence/decode_cpm','r2',str(source)],capture_output=True,text=True,check=True)
        original=json.loads(decoded.stdout)
        assert convert['legacy_valid'] and convert['legacy_roundtrip']
        assert convert['station_id']==original['station_id'] and convert['reference_time_ms']==original['reference_time_ms']
        assert convert['legacy_delta_ms']==original['reference_time_ms']%65536
        assert [o['id'] for o in convert['objects']]==[o['id'] for o in original['objects']]
        for a,b in zip(original['objects'],convert['objects']):
            for axis in ['x','y','z']:
                if axis+'_m' in a: assert abs(a[axis+'_m']*100-b[axis+'_cm'])<1e-8
            for axis in ['vx','vy']:
                if axis+'_m_s' in a: assert abs(a[axis+'_m_s']*100-b[axis+'_cm_s'])<1e-8
                else: assert b[axis+'_cm_s']==16383 and not b['velocity_available']
            assert a['measurement_delta_ms']==b['measurement_delta_ms']
            assert a['acceleration_present']==b['acceleration_present']
        assert checks['checks']['complete']==False and checks['result']==0
        results.append({'corpus':label,'index':i,'sha256':hashlib.sha256(data).hexdigest(),
            'source':str(source),'conversion':convert,'control':checks})
        if label=='a1live' and i<10: replay.append(str(source))
(case/'replay-index.json').write_text(json.dumps(replay,indent=2))
summary={'packets':len(results),'converted':len(results),'historical_roundtrips':len(results),
    'evaluated_speed_checks':sum(len(r['control']['checks']['evaluated']) for r in results),
    'messages_non_evaluable':sum(r['control']['checks']['verdict']=='non_evaluable' for r in results),
    'anomalies':sum(r['control']['checks']['anomalies'] for r in results),'results':results}
(out/'summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k!='results'},indent=2))
