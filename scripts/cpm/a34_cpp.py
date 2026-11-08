"""Compile just an ASN.1 comparison utility; F2MD production objects untouched."""
import hashlib,json,os,pathlib,subprocess
root=pathlib.Path('/repo'); case=pathlib.Path(os.environ['EXFMD_A34_CASE']); out=case/'cpm'; out.mkdir(exist_ok=False)
build=root/'results/phase3/calibration-20261108-190113/build'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(build/'libartery_F2MD.so')=='1d18655c07c943b0514d2453d139eb1b004329edcefe09a3bd05193d5557e229'
env=dict(os.environ,LD_LIBRARY_PATH=str(build)+':/repo/results/phase1/a1-e2e-20261106-161848/build:/omnetpp/lib:'+os.environ.get('LD_LIBRARY_PATH',''))
regressions={}
for name in ['test_a2','test_a3','test_calibration']:
    r=subprocess.run([str(build/name)],env=env,capture_output=True,text=True,check=True)
    (out/(name+'.stdout')).write_text(r.stdout); regressions[name]=json.loads(r.stdout)
lib='/artery/build/extern/vanetza/lib'
cmd=['g++-10','-std=c++17','-I/repo','-I/artery/extern/vanetza','-I/artery/extern/vanetza/vanetza/asn1/support',
    '/repo/scripts/cpm/a34_encode.cpp','-L'+lib,'-Wl,-rpath,'+lib,'-lvanetza_asn1','-lvanetza_asn1_its_r2','-lvanetza_asn1_its','-lvanetza_asn1_support','-o',str(out/'a34_encode')]
r=subprocess.run(cmd,capture_output=True,text=True); (out/'compile.log').write_text(r.stdout+r.stderr); r.check_returncode()
subprocess.run([str(out/'a34_encode'),str(case/'cpm-index.json'),str(out)],env=env,check=True)
(out/'manifest.json').write_text(json.dumps({'command':cmd,'source_sha256':sha(root/'scripts/cpm/a34_encode.cpp'),
    'f2md_sha256_unchanged':sha(build/'libartery_F2MD.so'),'regressions':regressions,'f2md_rebuilt':False},indent=2))
