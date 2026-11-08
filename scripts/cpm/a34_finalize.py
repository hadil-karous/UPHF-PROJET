import hashlib,json,os,pathlib
root=pathlib.Path('/repo'); case=pathlib.Path(os.environ['EXFMD_A34_CASE'])
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p): return json.loads(p.read_text())
qualified=load(root/'results/phase3/qualification-20261108-192445/source-hashes.json')
production={p:sha(root/p)==h for p,h in qualified.items() if p.startswith('cosimulation/carla_multi_agent/')}
assert production and all(production.values()),production
f2md=load(root/'results/phase3/calibration-20261108-190113/build/manifest.json')
cpp={p:sha(root/p)==h for p,h in f2md['source_hashes'].items()}; assert all(cpp.values()),cpp
assert load(case/'tests/python-tests.json')['passed']
comparison=load(case/'cpm/comparison.json'); assert comparison['passed']
assert comparison['baseline_exact_packets']==comparison['candidate_valid_packets']==38
differences=[]
for packet in comparison['comparisons']:
    for baseline,candidate in zip(packet['baseline'],packet['cwa_q2']):
        differences.append({'frame_id':packet['frame_id'],'capture_index':packet['capture_index'],'id':baseline['id'],
            **{k:(candidate[k]-v) for k,v in baseline.items() if k in ['x_cm','y_cm','z_cm','vx_cm_s','vy_cm_s']}})
(case/'cpm/decoded-differences.json').write_text(json.dumps(differences,indent=2))
summary={'passed':True,'production_source_unchanged':production,'f2md_sources_unchanged':all(cpp.values()),
    'python_tests':load(case/'tests/python-tests.json'),'settings_compared':16,
    'map_validation':load(case/'offline-map-validation.json'),
    'baseline_exact_cpm':38,'experimental_valid_cpm':38,'experimental_changed_cpm':comparison['candidate_changed_packets'],
    'production_promoted':False,'geometric_point_changed':False,'new_sensor_simulation_run':False,
    'f2md_thresholds_or_controls_changed':False}
(case/'summary.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2))
sources=[root/'experiments/tracker_a34.py',root/'tests/cpm/test_tracker_a34.py',root/'scripts/cpm/stability_a34.py',root/'scripts/cpm/run-a34-stability.ps1']
sources+=list((root/'scripts/cpm').glob('a34_*'))
hashes={}
for p in sources:
    if p.is_file():
        dst=case/'sources'/p.relative_to(root); dst.parent.mkdir(parents=True,exist_ok=True); dst.write_bytes(p.read_bytes())
        hashes[str(p.relative_to(root))]=sha(p)
(case/'source-hashes.json').write_text(json.dumps(hashes,indent=2))
