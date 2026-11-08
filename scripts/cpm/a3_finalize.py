"""Archive exact sources and verify build inputs after the executed validation."""
import hashlib,json,os,pathlib,subprocess
root=pathlib.Path('/repo'); case=pathlib.Path(os.environ['EXFMD_A3_CASE'])
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((case/'build/manifest.json').read_text())
for relative,expected in manifest['source_hashes'].items(): assert sha(root/relative)==expected, relative
assert sha(case/'build/libartery_F2MD.so')==manifest['patched_f2md_sha256']
original=pathlib.Path('/artery/build/src/artery/application/F2MD/libartery_F2MD.so')
assert sha(original)==manifest['original_f2md_sha256']
files=list((root/'scripts/cpm').glob('a3_*'))+[root/'scripts/cpm/run-a3-validation.ps1',root/'tests/cpm/test_a3.cpp',
    root/'artery-services/F2MD/F2MD_CPService.h',root/'artery-services/F2MD/F2MD_CPService.cc',
    root/'artery-services/F2MD/F2MD_CPFacility.cc',root/'artery-services/F2MD/mdFiles/mdChecks/CpmChecks.cc',
    root/'artery-services/F2MD/A3ReplayService.cc',root/'artery-services/F2MD/A3ReplayService.ned',
    root/'artery-services/cpm/R2ToLegacy.h',root/'artery-services/cpm/R2Temporal.h',root/'artery-services/cpm/TemporalPlausibility.h']
for p in files:
    destination=case/'sources'/p.relative_to(root); destination.parent.mkdir(parents=True,exist_ok=True); destination.write_bytes(p.read_bytes())
(case/'source-hashes.json').write_text(json.dumps({str(p.relative_to(root)):sha(p) for p in files},indent=2))
native=max(p for p in case.glob('native-*') if p.is_dir())
summary={'passed':True,'build_sources_current':True,'original_f2md_unchanged':True,
    'a2_units':json.loads((case/'build/test_a2.json').read_text()),
    'a3_units':json.loads((case/'build/test_a3.json').read_text()),
    'recorded_directory':(case/'recorded-latest.txt').read_text().strip(),
    'native_directory':native.name,'native_verification':json.loads((native/'verification.json').read_text())}
assert summary['native_verification']['passed']
(case/'summary.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2))
