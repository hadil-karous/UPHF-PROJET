"""Verify each native receiver's converted bytes and decisions against the
offline results for the same original R2 payload. No simulation is executed."""
import json,os,pathlib,hashlib
case=pathlib.Path(os.environ['EXFMD_A2_CASE'])
native=max(case.glob('native-*'),key=lambda p:p.name)
offline=json.loads((case/'recorded/summary.json').read_text())['results']
byhex={pathlib.Path(r['source']).read_bytes().hex():r for r in offline}
events={}
for path in (native/'events').glob('*.jsonl'):
    for line in path.read_text().splitlines():
        event=json.loads(line); events.setdefault((event['receiver'],event['event_id']),[]).append(event)
comparisons=[]
for (receiver,identifier),sequence in events.items():
    assert [e['stage'] for e in sequence]==['receive','decode','convert','control','non_evaluable']
    decoded=sequence[1]; converted=sequence[2]; controlled=sequence[3]
    source=byhex[decoded['source_r2_hex']]
    prefix=pathlib.Path(source['source']).with_name(pathlib.Path(source['source']).stem.replace('input-','converted-'))
    assert converted['legacy_hex']==prefix.with_suffix('.uper').read_bytes().hex()
    assert converted['objects']==source['conversion']['objects']
    assert converted['reference_time_ms']==source['conversion']['reference_time_ms']
    assert controlled['checks']==source['control']['checks']
    assert controlled['result']==source['control']['result']
    assert controlled['checks']['complete']==False
    comparisons.append({'receiver':receiver,'event_id':identifier,'source_sha256':source['sha256'],
        'legacy_sha256':hashlib.sha256(bytes.fromhex(converted['legacy_hex'])).hexdigest(),
        'reference_time_ms':converted['reference_time_ms'],'legacy_delta_ms':converted['legacy_delta_ms'],
        'objects':converted['objects'],'checks':controlled['checks']})
result={'passed':True,'native_messages_compared':len(comparisons),
    'exact_legacy_payload_matches':len(comparisons),'exact_control_matches':len(comparisons),
    'comparisons':comparisons}
assert len(comparisons)==20
(native/'verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='comparisons'},indent=2))
