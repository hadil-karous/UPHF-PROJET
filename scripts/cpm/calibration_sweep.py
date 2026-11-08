"""Run real linked F2MD over immutable A3 inputs for fixed policy candidates."""
import collections,json,os,pathlib,subprocess
root=pathlib.Path('/repo'); case=pathlib.Path(os.environ['EXFMD_A3_CASE'])
old=root/'results/phase3/a3-20261108-182931'; native=old/'native-20261108-174221-383958'
label=os.environ.get('EXFMD_CALIBRATION_STAGE','before')
out=case/('sweep-'+label); out.mkdir(exist_ok=False)
build=old/'build' if label=='before' else case/'build'
env=dict(os.environ,LD_LIBRARY_PATH=str(build)+':/repo/results/phase1/a1-e2e-20261106-161848/build:/omnetpp/lib:'+os.environ.get('LD_LIBRARY_PATH',''))
original=json.loads((native/'offline-index.json').read_text())
policies=[
    ('native_a3',1.6,4.6,90,3,'actual A3 native policy'),
    ('configured',3,4.5,90,3,'existing NED accel/decel restored; FoV-independent position tolerance unchanged'),
    ('repository_header',3,4.5,90,4,'existing F2MD_CPParameters defaults; candidate, not fitted to zero'),
    ('direction_120',3,4.5,120,4,'direction-rate sensitivity only; not validated physical policy'),
    ('direction_180',3,4.5,180,4,'direction-rate sensitivity only; not selected'),
    ('wide',6,6,120,4,'broader acceleration/deceleration sensitivity; not selected'),
    ('loose_negative_control',10,10,360,10,'deliberately loose sensitivity control; not selected')]
summaries=[]
frozen=json.loads((native/'anomalies.json').read_text())
frozen_rows=json.loads((native/'offline-controls.json').read_text())
frozen_by_key={(r['provenance']['receiver'],r['provenance']['capture_index']):r for r in frozen_rows}
for name,acc,dec,turn,excess,why in policies:
    entries=json.loads(json.dumps(original))
    for e in entries:
        e['path']=str(root/'results/phase3'/pathlib.Path(e['path']).relative_to('/evidence'))
        e['parameters'].update(acceleration_m_s2=acc,deceleration_m_s2=dec,angular_rate_deg_s=turn,excess_speed_m_s=excess)
    source=out/(name+'-index.json'); source.write_text(json.dumps(entries,indent=2))
    destination=out/(name+'-controls.json')
    subprocess.run([str(build/'test_a3'),str(source),str(destination)],env=env,check=True)
    results=json.loads(destination.read_text()); checks=collections.Counter(); actions=collections.Counter(); anomalies=[]
    for r in results:
        c=r['control']; assert c['verdict']!='technical_error' and not c['complete']
        for row in c['checks']:
            checks[(row['check'],row['status'])]+=1
            if row['status']=='anomaly': anomalies.append({**row,'receiver':c['receiver'],'frame_id':r['provenance']['frame_id'],'capture_index':r['provenance']['capture_index']})
        actions.update(s['history_action'] for s in c['history'])
    frozen_count=collections.Counter()
    for a in frozen:
        if a['check']=='speed_consistency':
            bound=(acc if a['speed_change_m_s']>=0 else dec)*a['dt_s']+2*(2**.5)*.005
            stays=abs(a['speed_change_m_s'])>bound
        elif a['check']=='direction_consistency':
            bound=a['allowed_change_deg']+(turn-90)*a['dt_s']; stays=a['angle_change_deg']>bound
        else:
            bound=a['allowed_distance_m']+(excess-3)*a['dt_s']; stays=a['displacement_m']>bound
        if stays: frozen_count[a['check']]+=1
    summaries.append({'name':name,'reason':why,'parameters':entries[0]['parameters'],'cpm':len(results),
        'anomalies':sum(v for (k,s),v in checks.items() if s=='anomaly'),
        'checks':[{'check':k,'status':s,'count':v} for (k,s),v in sorted(checks.items())],
        'history_actions':dict(actions),'anomaly_observations':anomalies,
        'fixed_original_40_pairs_retained':dict(frozen_count),
        'early_anomalies':sum(a['frame_id']<1189 for a in anomalies),
        'late_anomalies':sum(a['frame_id']>=1189 for a in anomalies)})
    print(name+': '+str(summaries[-1]['anomalies'])+' exceedances',flush=True)
if label=='before':
    assert summaries[0]['anomalies']==40
    expected=json.loads((native/'offline-controls.json').read_text())
    current=json.loads((out/'native_a3-controls.json').read_text())
    assert [e['control'] for e in expected]==[e['control'] for e in current]
(out/'summary.json').write_text(json.dumps(summaries,indent=2))
