"""Build just changed F2MD translation units using the original image objects."""
import hashlib,json,os,pathlib,shlex,subprocess
root=pathlib.Path('/repo'); case=pathlib.Path(os.environ['EXFMD_A3_CASE']); out=case/'build'; out.mkdir(exist_ok=True)
base=pathlib.Path('/artery/build/src/artery/application/F2MD')
core=root/'results/phase1/a1-e2e-20261106-161848/build/libartery_core.so'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
original=base/'libartery_F2MD.so'; before=sha(original)
assert before=='b961e773616bed2684fec6a8c6bae0c0788df539b89b3e292bac6eead1616e51'
for relative in ['F2MD_CPService.h','F2MD_CPFacility.cc']:
    assert (root/'results/audit-support/container-sources/artery/F2MD'/relative).read_bytes()==(pathlib.Path('/artery/src/artery/application/F2MD')/relative).read_bytes()
args=[]
for line in (base/'CMakeFiles/F2MD.dir/flags.make').read_text().splitlines():
    if line.startswith(('CXX_DEFINES =','CXX_INCLUDES =','CXX_FLAGS =')): args+=shlex.split(line.split('=',1)[1])
args+=['-O1','-I/repo','-I/repo/artery-services/cpm','-I/artery/src/artery/application/F2MD','-I/artery/src/artery/application/F2MD/mdFiles/mdChecks']
headers=list((root/'artery-services/cpm').glob('*.h'))+[root/'artery-services/F2MD/F2MD_CPService.h']
sources=[root/'artery-services/F2MD'/s for s in ['F2MD_CPService.cc','F2MD_CPFacility.cc','mdFiles/mdChecks/CpmChecks.cc','A3ReplayService.cc']]
test_names=['test_a2','test_a3']+(['test_calibration'] if os.environ.get('EXFMD_CALIBRATION_TESTS')=='1' else [])
hashes={str(p.relative_to(root)):sha(p) for p in headers+sources+[root/'tests/cpm'/(n+'.cpp') for n in test_names]+[pathlib.Path(__file__)]}
prior=json.loads((out/'manifest.json').read_text()) if (out/'manifest.json').exists() else {}
def compile_logged(cmd,label):
    process=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (out/(label+'.compile.log')).write_text(process.stdout)
    if process.returncode:
        print(process.stdout,flush=True); process.check_returncode()
same_headers=all(prior.get('source_hashes',{}).get(str(p.relative_to(root)))==sha(p) for p in headers)
commands=[]; replacements={}
for source in sources:
    target=out/(source.stem+'.o')
    cmd=['g++-10',*args,'-c',str(source),'-o',str(target)]; commands.append(cmd)
    if not (same_headers and target.exists() and prior.get('source_hashes',{}).get(str(source.relative_to(root)))==sha(source)):
        print('Compiling '+source.name,flush=True); compile_logged(cmd,source.stem)
    replacements['CMakeFiles/F2MD.dir/'+str(source.relative_to(root/'artery-services/F2MD'))+'.o']=str(target)
link=shlex.split((base/'CMakeFiles/F2MD.dir/link.txt').read_text())
link[link.index('-o')+1]=str(out/'libartery_F2MD.so'); link=[replacements.get(a,a) for a in link]
link.append(str(out/'A3ReplayService.o'))
linked=subprocess.run(link,cwd=base,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
(out/'link.log').write_text(linked.stdout); linked.check_returncode(); commands.append(link)
assert sha(original)==before
env=dict(os.environ,LD_LIBRARY_PATH=str(out)+':'+str(core.parent)+':/omnetpp/lib:'+os.environ.get('LD_LIBRARY_PATH',''))
lib='/artery/build/extern/vanetza/lib'
deps=['-L'+str(out),'-Wl,-rpath,'+str(out),'-l:libartery_F2MD.so',
    '-L/artery/build/src/artery/envmod','-Wl,-rpath,/artery/build/src/artery/envmod','-l:libartery_envmod.so',
    '-L'+str(core.parent),'-Wl,-rpath,'+str(core.parent),'-l:libartery_core.so',
    '-L/omnetpp/lib','-Wl,-rpath,/omnetpp/lib','-loppenvir','-loppsim',
    '-L/artery/extern/inet/out/gcc-release/src','-Wl,-rpath,/artery/extern/inet/out/gcc-release/src','-lINET',
    '/artery/build/extern/libveins.so','/artery/build/src/traci/libtraci.so',
    '-L'+lib,'-Wl,-rpath,'+lib,'-lvanetza_asn1','-lvanetza_asn1_its_r2','-lvanetza_asn1_its','-lvanetza_asn1_support']
for name in test_names:
    cmd=['g++-10',*args,str(root/'tests/cpm'/(name+'.cpp')),*deps,'-o',str(out/name)]
    print('Compiling '+name,flush=True); compile_logged(cmd,name); commands.append(cmd)
    run=subprocess.run([str(out/name)],text=True,capture_output=True,env=env)
    (out/(name+'.stdout')).write_text(run.stdout); (out/(name+'.stderr')).write_text(run.stderr)
    print(run.stdout+run.stderr,flush=True)
    if run.returncode: raise RuntimeError(name+' failed; see evidence logs')
    (out/(name+'.json')).write_text(run.stdout)
ldd=subprocess.run(['ldd',str(out/'libartery_F2MD.so')],env=env,capture_output=True,text=True,check=True).stdout
(out/'ldd.txt').write_text(ldd); assert 'not found' not in ldd
assert all(sha(root/relative)==value for relative,value in hashes.items()), 'source modified during build; rebuild required'
manifest={'source_hashes':hashes,'commands':commands,'patched_f2md_sha256':sha(out/'libartery_F2MD.so'),
    'original_f2md_sha256':before,'original_unchanged':sha(original)==before,'a1_core_sha256':sha(core),
    'compiler':subprocess.check_output(['g++-10','--version'],text=True),'image_headers_verified':True}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2))
for p in headers+sources+[root/'tests/cpm/test_a3.cpp']:
    dest=case/'sources'/p.relative_to(root); dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(p.read_bytes())
print('A3 built and C++ tests passed; original image libraries unchanged',flush=True)
