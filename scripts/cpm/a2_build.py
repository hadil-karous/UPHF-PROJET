"""Inside the isolated image, build only the A2 adapter/service/check objects."""
import hashlib,json,os,pathlib,shlex,subprocess
root=pathlib.Path('/repo'); build=pathlib.Path('/artery/build/src/artery/application/F2MD')
out=pathlib.Path(os.environ['EXFMD_A2_BUILD']); out.mkdir(parents=True,exist_ok=True)
lib='/artery/build/extern/vanetza/lib'
common=['-std=c++17','-I/repo','-I/artery/extern/vanetza','-I/artery/extern/vanetza/vanetza/asn1/support',
    '-L'+lib,'-Wl,-rpath,'+lib,'-lvanetza_asn1','-lvanetza_asn1_its_r2','-lvanetza_asn1_its','-lvanetza_asn1_support']
prior=json.loads((out/'manifest.json').read_text()) if (out/'manifest.json').exists() else {}
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
header='artery-services/cpm/R2ToLegacy.h'
header_same=prior.get('source_hashes',{}).get(header)==digest(root/header)
if not (header_same and (out/'a2_convert').exists()):
    subprocess.run(['g++','/repo/scripts/cpm/a2_convert.cpp',*common,'-o',str(out/'a2_convert')],check=True)
args=[]
for line in (build/'CMakeFiles/F2MD.dir/flags.make').read_text().splitlines():
    if line.startswith(('CXX_DEFINES =','CXX_INCLUDES =','CXX_FLAGS =')): args+=shlex.split(line.split('=',1)[1])
args+=['-I/repo/artery-services/cpm','-I/artery/src/artery/application/F2MD','-I/artery/src/artery/application/F2MD/mdFiles/mdChecks']
replacements={}
for relative in ['F2MD_CPService.cc','mdFiles/mdChecks/CpmChecks.cc']:
    target=out/(pathlib.Path(relative).stem+'.o')
    source=root/'artery-services/F2MD'/relative
    source_same=prior.get('source_hashes',{}).get(str(source.relative_to(root)))==digest(source)
    if not (header_same and source_same and target.exists()):
        subprocess.run(['g++-10',*args,'-c',str(source),'-o',str(target)],check=True)
    replacements['CMakeFiles/F2MD.dir/'+relative+'.o']=str(target)
original=build/'libartery_F2MD.so'; digest=hashlib.sha256(original.read_bytes()).hexdigest()
link=shlex.split((build/'CMakeFiles/F2MD.dir/link.txt').read_text())
link[link.index('-o')+1]=str(out/'libartery_F2MD.so')
link=[replacements.get(arg,arg) for arg in link]
replay=out/'A2ReplayService.o'
subprocess.run(['g++-10',*args,'-c',str(root/'artery-services/F2MD/A2ReplayService.cc'),'-o',str(replay)],check=True)
link.append(str(replay))
subprocess.run(link,cwd=build,check=True)
assert digest==hashlib.sha256(original.read_bytes()).hexdigest()
(out/'manifest.json').write_text(json.dumps({'original_f2md_sha256':digest,'original_unchanged':True,
    'patched_f2md_sha256':hashlib.sha256((out/'libartery_F2MD.so').read_bytes()).hexdigest(),
    'compile_flags':args,'link':link,'source_hashes':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [root/'artery-services/F2MD/F2MD_CPService.cc',root/'artery-services/F2MD/mdFiles/mdChecks/CpmChecks.cc',root/'artery-services/F2MD/A2ReplayService.cc',root/'artery-services/cpm/R2ToLegacy.h']}},indent=2))
print('A2 component built; original F2MD unchanged')
core=pathlib.Path(os.environ['EXFMD_A1_CORE'])
os.environ['LD_LIBRARY_PATH']=str(out)+':'+str(core.parent)+':/omnetpp/lib:'+os.environ.get('LD_LIBRARY_PATH','')
deps=['-L'+str(out),'-Wl,-rpath,'+str(out),'-l:libartery_F2MD.so',
    '-L/artery/build/src/artery/envmod','-Wl,-rpath,/artery/build/src/artery/envmod','-l:libartery_envmod.so',
    '-L'+str(core.parent),'-Wl,-rpath,'+str(core.parent),'-l:libartery_core.so',
    '-L/omnetpp/lib','-Wl,-rpath,/omnetpp/lib','-loppenvir','-loppsim',
    '-L/artery/extern/inet/out/gcc-release/src','-Wl,-rpath,/artery/extern/inet/out/gcc-release/src','-lINET',
    '/artery/build/extern/libveins.so','/artery/build/src/traci/libtraci.so']
subprocess.run(['g++-10',*args,'-I/repo','/repo/tests/cpm/test_a2.cpp',*deps,*common,
    '-o',str(out/'test_a2')],check=True)
result=subprocess.run([str(out/'test_a2')],capture_output=True,text=True)
(out/'unit-tests.stdout').write_text(result.stdout); (out/'unit-tests.stderr').write_text(result.stderr)
print(result.stdout,result.stderr)
result.check_returncode()
(out/'unit-tests.json').write_text(result.stdout)
