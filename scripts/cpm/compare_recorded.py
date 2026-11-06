"""Inside the isolated image: decode the saved real corpus, including legacy failures.
No simulated clock or input data is changed.
"""
import hashlib
import json
from pathlib import Path
import subprocess

root=Path('/repo/results/integrated/run-20261105-151425')
out=Path('/evidence/corrections/recorded'); out.mkdir(exist_ok=True)
records=[json.loads(line) for line in (root/'ros-messages.jsonl').open()]
perceptions=[json.loads(r['message']['data']) for r in records if r['topic']=='/carla/hero/perceived_objects']
summaries=[]
for index,record in enumerate(r for r in records if r['topic'].endswith('/cpm')):
    packet=bytes.fromhex(record['message']['hex']); payload=packet[44:]
    path=out/('cpm-'+str(index)+'.uper'); path.write_bytes(payload)
    decoders={}
    for fmt in ['r2','legacy']:
        result=subprocess.run(['/evidence/decode_cpm',fmt,str(path)],capture_output=True,text=True)
        decoders[fmt]=json.loads(result.stdout)
        decoders[fmt]['process_exit_code']=result.returncode
        decoders[fmt]['stderr']=result.stderr
    assert decoders['r2']['valid'] and decoders['r2']['consumed_bytes']==len(payload)
    assert not decoders['legacy']['decoded']
    # Position-only nearest match is explicitly not an exact temporal pairing.
    def distance(p):
        if len(p['objects'])!=len(decoders['r2']['objects']): return float('inf')
        return sum((a['x']-b['x_m'])**2+(a['y']-b['y_m'])**2 for a,b in zip(p['objects'],decoders['r2']['objects']))
    nearest=min(perceptions,key=distance)
    summaries.append({'index':index,'payload_sha256':hashlib.sha256(payload).hexdigest(),
        'decoders':decoders,'nearest_perception_by_position_only':nearest,
        'position_squared_error_m2':distance(nearest),
        'exact_measurement_pairing':False})
(out/'comparison.json').write_text(json.dumps({'packets':len(summaries),'r2_valid':len(summaries),
    'legacy_failures':len(summaries),'results':summaries},indent=2))
print('Saved real corpus: %d R2 valid / %d legacy RC_FAIL' % (len(summaries),len(summaries)))
