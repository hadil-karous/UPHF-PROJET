"""Validate real native F2MD RX against live CPM bytes, frame lineage and CpmChecks."""
import argparse,collections,csv,hashlib,json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
BUILD='/repo/results/phase3/calibration-20261108-190113/build'
def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',required=True);a=p.parse_args();out=pathlib.Path(a.attempt).resolve()
    validation=json.loads((out/'validation-01/validation.json').read_text());assert validation['passed']
    rows=list(csv.DictReader((out/'validation-01/object-comparisons.csv').open()))
    bysha={r['payload_sha256']:r for r in rows}
    groups=collections.defaultdict(list)
    for f in (out/'f2md-events').glob('*.jsonl'):
        for line in f.read_text().splitlines():
            e=json.loads(line);groups[e['receiver'],e['event_id']].append(e)
    assert groups,'No native F2MD reception'
    entries=[];originals=[];linked=[];errors=[];counts=collections.Counter()
    for (receiver,event),events in sorted(groups.items()):
        assert [e['stage'] for e in events]==['receive','decode','convert','control','non_evaluable'],events
        digest=hashlib.sha256(bytes.fromhex(events[1]['source_r2_hex'])).hexdigest();assert digest in bysha
        row=bysha[digest];c=events[3];checks=c['checks']
        assert c['facility_called'] and c['temporal_checks_called'] and not checks['complete']
        assert checks['reference_time_ms']==int(row['reference_tai_ms'])
        assert checks['receive_time_ms']>=checks['reference_time_ms']
        policy=checks['policy']
        for key,val in {'acceleration_m_s2':3,'deceleration_m_s2':4.5,'angular_rate_deg_s':90,'excess_speed_m_s':3,'speed_limit_m_s':4.1}.items():assert abs(policy[key]-val)<1e-9
        path=out/'validation-01'/('packet-%03d.uper'%int(row['capture_index']))
        entry={'path':'/repo/'+path.relative_to(ROOT).as_posix(),'sha256':digest,'receiver':receiver,
            'receive_time_ms':checks['receive_time_ms'],'parameters':policy}
        entries.append(entry);originals.append(checks)
        for h in checks['history']:
            assert h['measurement_time_ms']==int(row['reference_tai_ms'])+int(row['measurement_delta_ms'])
            assert any(r['track_id']==str(h['id']) and r['payload_sha256']==digest for r in rows)
        for result in checks['checks']:
            counts[result['check'],result['status']]+=1
            linked.append({'receiver':receiver,'event_id':event,'station':checks['station'],'frame_id':int(row['frame_id']),
                'payload_sha256':digest,'simulation_time_s':c['simulation_time_s'],
                'reference_time_ms':checks['reference_time_ms'],'receive_time_ms':checks['receive_time_ms'],**result})
    (out/'native-replay-index.json').write_text(json.dumps(entries,indent=2))
    linux='/repo/'+out.relative_to(ROOT).as_posix()
    cmd=['docker','exec','-e','LD_LIBRARY_PATH='+BUILD+':/repo/results/phase1/a1-e2e-20261106-161848/build:/omnetpp/lib',
        'exfmd-artery',BUILD+'/test_a3',linux+'/native-replay-index.json',linux+'/native-recalculated.json']
    subprocess.run(cmd,check=True)
    actual=json.loads((out/'native-recalculated.json').read_text());assert len(actual)==len(originals)
    assert all(e['control']==c for e,c in zip(actual,originals))
    log=(out/'artery.log').read_text();assert 'Node mbType=LocalAttacker' not in log
    assert log.count('Node mbType=Genuine prob=0')==2
    receivers=sorted({k[0] for k in groups});assert len(receivers)==2
    (out/'f2md-linked-checks.json').write_text(json.dumps(linked,indent=2))
    result={'passed':True,'radio_received':len(groups),'r2_decoded':len(entries),'converted':len(entries),
        'facility_calls':len(originals),'temporal_calls':len(originals),'exact_native_recalculations':len(actual),
        'receivers':receivers,'technical_errors':0,'conversion_rejections':0,'policy':policy,
        'checks':[{'check':k[0],'status':k[1],'count':v} for k,v in sorted(counts.items())],
        'temporal_anomaly_occurrences':sum(v for (k,s),v in counts.items() if s=='anomaly' and k!='speed_plausibility'),
        'a1':validation,'source':'live CARLA/SUMO/ROS/Artery/F2MD; no packet replay transmitter',
        'native_receptions_are_not_ros_copies':True}
    (out/'validation-a4.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
