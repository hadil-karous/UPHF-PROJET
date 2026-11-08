"""Run the immutable calibrated F2MD tests; build only a new ASN.1 test utility."""
import datetime,hashlib,json,os,pathlib,subprocess
root=pathlib.Path('/repo'); case=pathlib.Path(os.environ['EXFMD_A3_CASE']); out=case/'cpp-tests'
if out.exists(): out=case/('cpp-tests-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
out.mkdir(exist_ok=False)
old=root/'results/phase3/calibration-20261108-190113'; build=old/'build'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((build/'manifest.json').read_text())
assert sha(build/'libartery_F2MD.so')==manifest['patched_f2md_sha256']=='1d18655c07c943b0514d2453d139eb1b004329edcefe09a3bd05193d5557e229'
for relative,value in manifest['source_hashes'].items(): assert sha(root/relative)==value, 'C++/builder changed: '+relative
env=dict(os.environ,LD_LIBRARY_PATH=str(build)+':/repo/results/phase1/a1-e2e-20261106-161848/build:/omnetpp/lib:'+os.environ.get('LD_LIBRARY_PATH',''))
results={}
for name in ['test_a2','test_a3','test_calibration']:
    run=subprocess.run([str(build/name)],env=env,capture_output=True,text=True,check=True)
    (out/(name+'.stdout')).write_text(run.stdout); (out/(name+'.stderr')).write_text(run.stderr)
    results[name]=json.loads(run.stdout); assert results[name]['passed']
lib='/artery/build/extern/vanetza/lib'
cmd=['g++-10','-std=c++17','-I/repo','-I/artery/extern/vanetza','-I/artery/extern/vanetza/vanetza/asn1/support',
    '/repo/scripts/cpm/qualification_roundtrip.cpp','-L'+lib,'-Wl,-rpath,'+lib,
    '-lvanetza_asn1','-lvanetza_asn1_its_r2','-lvanetza_asn1_its','-lvanetza_asn1_support','-o',str(out/'qualification_roundtrip')]
compiled=subprocess.run(cmd,capture_output=True,text=True)
(out/'compile.log').write_text(compiled.stdout+compiled.stderr); compiled.check_returncode()
subprocess.run([str(out/'qualification_roundtrip'),str(case/'fixture-index.json'),str(out/'roundtrips.json')],env=env,check=True)
roundtrips=json.loads((out/'roundtrips.json').read_text()); assert roundtrips['packets']==38 and roundtrips['passed']
assert sha(build/'libartery_F2MD.so')==manifest['patched_f2md_sha256']
recorded=case/'recorded'; recorded.mkdir()
# Actual ordered CpmChecks replay with the unchanged restored policy.
entries=json.loads((old/'native-20261108-181019-177625/offline-index.json').read_text())
for entry in entries: entry['path']='/repo/results/phase3/'+str(pathlib.Path(entry['path']).relative_to('/evidence'))
(recorded/'index.json').write_text(json.dumps(entries,indent=2))
subprocess.run([str(build/'test_a3'),str(recorded/'index.json'),str(recorded/'controls.json')],env=env,check=True)
after=json.loads((recorded/'controls.json').read_text()); before=json.loads((old/'native-20261108-181019-177625/offline-controls.json').read_text())
assert [r['control'] for r in after]==[r['control'] for r in before]
(recorded/'summary.json').write_text(json.dumps({'passed':True,'exact_f2md_decisions':len(after),'anomalies':sum(r['control']['anomalies'] for r in after)},indent=2))
(case/'recorded-latest.txt').write_text('recorded')
results.update(passed=True,roundtrips=38,f2md_recompiled=False,f2md_sha256=manifest['patched_f2md_sha256'],test_utility_command=cmd,
    utility_source_sha256=sha(root/'scripts/cpm/qualification_roundtrip.cpp'))
(out/'summary.json').write_text(json.dumps(results,indent=2)); print(json.dumps({k:results[k] for k in ['passed','roundtrips','f2md_recompiled','f2md_sha256']},indent=2))
(case/'cpp-tests-latest.txt').write_text(out.name)
