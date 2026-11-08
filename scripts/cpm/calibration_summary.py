"""Aggregate executed before/after comparisons; no simulation or threshold fit."""
import collections,hashlib,json,os,pathlib
root=pathlib.Path('/repo'); case=pathlib.Path(os.environ['EXFMD_A3_CASE'])
def load(p): return json.loads(p.read_text())
before=load(case/'sweep-before/summary.json'); after=load(case/'sweep-after/summary.json')
native=sorted(p for p in case.glob('native-*') if p.is_dir())
assert len(native)==2
baseline,selected=native
def count(path):
    result=load(path/'result.json'); verification=load(path/'verification.json')
    assert verification['passed'] and result['exit_code']==0 and not result['technical_errors']
    anomalies={r['check']:r['count'] for r in result['checks'] if r['status']=='anomaly'}
    return {'directory':path.name,'anomalies':sum(anomalies.values()),'anomalies_by_check':anomalies,
        'result':result,'verification':verification}
a=count(baseline); b=count(selected)
assert a['anomalies']==after[0]['anomalies']==38 and b['anomalies']==after[1]['anomalies']==24
transitions=[]
for entry in load(baseline/'offline-index.json'):
    assert entry['parameters']['acceleration_m_s2']==1.6
for entry in load(selected/'offline-index.json'):
    assert entry['parameters']['acceleration_m_s2']==3 and entry['parameters']['deceleration_m_s2']==4.5
    assert entry['parameters']['angular_rate_deg_s']==90 and entry['parameters']['excess_speed_m_s']==3
    assert entry['parameters']['speed_limit_m_s']==4.1
for old,new in zip(before,after):
    assert old['name']==new['name']
    transitions.append({'name':old['name'],'parameters':new['parameters'],'before_cpp_fix':old['anomalies'],
        'after_cpp_fix':new['anomalies'],'fixed_original_40_pairs_retained':new['fixed_original_40_pairs_retained'],
        'early_anomalies':new['early_anomalies'],'late_anomalies':new['late_anomalies'],
        'checks_after':new['checks']})
# Attribute changes by original source event, not native receiver-number coincidence.
old_anomalies=load(root/'results/phase3/a3-20261108-182931/native-20261108-174221-383958/anomalies.json')
initial={(r['receiver'],r['capture_index'],r['id'],r['check']):r for r in old_anomalies}
new=load(selected/'anomalies.json'); kept={(r['receiver'],r['capture_index'],r['id'],r['check']) for r in new}
assert kept.issubset(initial)
for key,row in initial.items(): transitions_label='retained' if key in kept else 'no longer exceeded under selected policy'; transitions.append({'original_case':row,'selected_policy_status':transitions_label})
summary={'passed':True,'selected_policy':'configured: existing NED temporal limits restored; direction/position thresholds unchanged',
    'old_native_exceedances':40,'fixed_code_baseline':a,'selected_native':b,
    'a2_units':load(case/'build/test_a2.json'),'a3_units':load(case/'build/test_a3.json'),
    'calibration_units':load(case/'build/test_calibration.json'),
    'a2_recorded_regression':load(case/'recorded/summary.json')['a2_regression'],
    'policies_and_source_case_transitions':transitions}
(case/'calibration-summary.json').write_text(json.dumps(summary,indent=2))
sources=list((root/'scripts/cpm').glob('calibration_*.py'))+[root/'scripts/cpm/run-calibration-validation.ps1',root/'tests/cpm/test_calibration.cpp']
for source in sources:
    if source.exists():
        target=case/'sources'/source.relative_to(root); target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(source.read_bytes())
(case/'calibration-source-hashes.json').write_text(json.dumps({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources if p.exists()},indent=2))
print(json.dumps({'passed':True,'before':40,'algorithm_fix_only':a['anomalies'],'selected_policy':b['anomalies'],
    'selected_anomalies_by_check':b['anomalies_by_check']},indent=2))
