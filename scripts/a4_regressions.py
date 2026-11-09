"""Compare the unchanged F2MD against the complete recorded A2/A3 baselines."""
import argparse,hashlib,json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1];BUILD='/repo/results/phase3/calibration-20261108-190113/build'
p=argparse.ArgumentParser();p.add_argument('--source',required=True);a=p.parse_args();case=pathlib.Path(a.source).resolve()
out=next(case/('recorded-regressions-%02d'%i) for i in range(1,100) if not (case/('recorded-regressions-%02d'%i)).exists());out.mkdir(exist_ok=False)
def command(*args):return subprocess.check_output(['docker',*args],text=True)
was_running=command('inspect','exfmd-artery','--format','{{.State.Running}}').strip()=='true'
try:
    if not was_running:command('start','exfmd-artery')
    ld=BUILD+':/repo/results/phase1/a1-e2e-20261106-161848/build:/omnetpp/lib'
    def evaluate(name,*args):
        return command('exec','-e','LD_LIBRARY_PATH='+ld,'exfmd-artery',BUILD+'/'+name,*args)
    old=ROOT/'results/phase3/calibration-20261108-190113/native-20261108-181019-177625'
    original=json.loads((old/'offline-controls.json').read_text())
    index=json.loads((old/'offline-index.json').read_text())
    for entry in index:
        if entry['path'].startswith('/evidence/'):entry['path']=entry['path'].replace('/evidence/','/repo/results/phase3/',1)
        assert entry['path'].startswith('/repo/')
        host=ROOT/entry['path'][len('/repo/'):]
        assert hashlib.sha256(host.read_bytes()).hexdigest()==entry['sha256']
    indexfile=out/'a3-index.json';indexfile.write_text(json.dumps(index,indent=2))
    target=out/'a3-controls.json'
    evaluate('test_a3','/repo/'+indexfile.relative_to(ROOT).as_posix(),'/repo/'+target.relative_to(ROOT).as_posix())
    current=json.loads(target.read_text());assert [c['control'] for c in current]==[c['control'] for c in original]
    baseline=ROOT/'results/phase1/a2-20261106-170909'
    entries=json.loads((baseline/'recorded/summary.json').read_text())['results'];speed=0
    for e in entries:
        source=baseline/'recorded'/e['corpus']/('input-%02d.uper'%e['index'])
        destination=out/('a2-%s-%02d.json'%(e['corpus'],e['index']))
        evaluate('test_a2','/repo/'+source.relative_to(ROOT).as_posix(),'/repo/'+destination.relative_to(ROOT).as_posix())
        now=json.loads(destination.read_text())
        assert now['checks']==e['control']['checks'] and now['result']==e['control']['result']
        speed+=len(now['checks']['evaluated'])
    result={'passed':True,'a2_messages_identical':len(entries),'a2_evaluated_speed_checks_identical':speed,
        'a3_native_decisions_identical':len(current),'a3_temporal_anomaly_occurrences':sum(r['status']=='anomaly' and r['check']!='speed_plausibility' for c in current for r in c['control']['checks']),
        'source_a3_index':str((old/'offline-index.json').relative_to(ROOT)),'simulation_launched':False}
    assert result['a2_messages_identical']==76 and speed==150 and len(current)==76 and result['a3_temporal_anomaly_occurrences']==24
    (out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
finally:
    if not was_running:command('stop','exfmd-artery')
