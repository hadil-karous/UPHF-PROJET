"""Collect saved evidence; does not execute or rerun tests."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[2]
out=root/'results/phase1'; corrections=out/'corrections'
def load(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def latest(prefix):
    results=[p for p in corrections.glob(prefix+'*/result.json') if load(p)['exit_code']==0]
    return max(results,key=lambda p:p.parent.name)
baseline=latest('baseline-'); integration=latest('integration-')
originals=load(out/'tests_a1_a2.json')
preserved={}
for run in originals['runs']:
    source=root/'results/integrated'/run/'ros-messages.jsonl'
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    preserved[run]={'sha256':digest,'unchanged':digest==originals['runs'][run]['jsonl_sha256']}
assert all(v['unchanged'] for v in preserved.values())
corpus=load(corrections/'recorded/comparison.json')
summary={'branch':'fix/cpm-f2md-integration','cpp':load(corrections/'cpp-tests.json'),
    'python':load(corrections/'python-tests.json'),
    'recorded':{k:corpus[k] for k in ('packets','r2_valid','legacy_failures')},
    'baseline':{'path':str(baseline.relative_to(root)),**load(baseline)},
    'integration':{'path':str(integration.relative_to(root)),**load(integration)},
    'build':load(corrections/'component-build.json'),'preserved_recordings':preserved}
(corrections/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps({'cpp':summary['cpp'],'python':summary['python'],'recorded':summary['recorded'],
    'baseline':str(baseline.relative_to(root)),'integration':str(integration.relative_to(root)),
    'preserved_recordings':all(v['unchanged'] for v in preserved.values())},indent=2))
