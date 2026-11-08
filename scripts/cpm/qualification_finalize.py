"""Verify the unchanged native result and archive the exact A3.3 sources."""
import hashlib,json,os,pathlib
root=pathlib.Path('/repo'); case=pathlib.Path(os.environ['EXFMD_A3_CASE'])
native=max(p for p in case.glob('native-*') if p.is_dir())
def load(p): return json.loads(p.read_text())
verification=load(native/'verification.json'); assert verification['passed'] and verification['anomaly_observations']==24
reference=root/'results/phase3/calibration-20261108-190113/native-20261108-181019-177625'
old=load(reference/'offline-controls.json'); new=load(native/'offline-controls.json')
assert [r['control'] for r in old]==[r['control'] for r in new], 'unchanged CPM/native policy produced different decision'
analysis=load(case/'analysis-validated/summary.json')
cpp=load(case/(case/'cpp-tests-latest.txt').read_text().strip()/'summary.json')
python=load(case/'python-tests-02/python-tests.json')
assert analysis['passed'] and cpp['passed'] and python['passed']
sources=[root/'cosimulation/carla_multi_agent'/name for name in ['fusion_detector.py','estimation_quality.py','perception_contract.py']]
sources += [root/'tests/cpm/test_estimation_quality.py']
sources += list((root/'scripts/cpm').glob('qualification_*'))
sources += [root/'scripts/cpm/a3_native.py',root/'scripts/cpm/a3_verify_native.py',root/'scripts/cpm/run-qualification-validation.ps1']
hashes={}
for p in sources:
    if p.is_file():
        destination=case/'sources'/p.relative_to(root); destination.parent.mkdir(parents=True,exist_ok=True); destination.write_bytes(p.read_bytes())
        hashes[str(p.relative_to(root))]=hashlib.sha256(p.read_bytes()).hexdigest()
(case/'source-hashes.json').write_text(json.dumps(hashes,indent=2))
summary={'passed':True,'analysis':analysis,'python_tests':python,
    'cpp_assertions':{k:cpp[k]['assertions'] for k in ['test_a2','test_a3','test_calibration']},
    'exact_uper_matches':cpp['roundtrips'],'f2md_recompiled':False,'f2md_sha256':cpp['f2md_sha256'],
    'native_directory':native.name,'native_verification':verification,'exact_native_decisions_to_previous_calibration':len(new)}
(case/'summary.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2))
