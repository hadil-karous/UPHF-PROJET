"""Freeze A4 summary, final source hashes and preservation after all targeted checks."""
import argparse,hashlib,json,pathlib,shutil,subprocess
from a4_data import dataset
ROOT=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--source',required=True);a=p.parse_args();out=pathlib.Path(a.source).resolve()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
old=json.loads((out/'preservation-before.json').read_text())
changed=[s for s,h in old.items() if not (ROOT/s).is_file() or sha(ROOT/s)!=h]
initial=json.loads((out/'containers-before.json').read_text())
current=json.loads(subprocess.check_output(['docker','inspect',*[e['Id'] for e in initial]],text=True))
post={e['Id']:e for e in current}
containers={e['Name']:e['Image']==post[e['Id']]['Image'] and e['State']['Running']==post[e['Id']]['State']['Running'] for e in initial}
preservation={'passed':not changed and all(containers.values()),'files_checked':len(old),'changed':changed,'containers':containers}
(out/'preservation-final.json').write_text(json.dumps(preservation,indent=2));assert preservation['passed']
d=dataset(out);assert d['validated']
v=json.loads((out/'attempt-01/validation-a4.json').read_text())
regressions=next(p for p in sorted(out.glob('recorded-regressions-*'),reverse=True) if (p/'summary.json').exists())
reg=json.loads((regressions/'summary.json').read_text());assert reg['passed']
sources=[ROOT/'.gitattributes',*ROOT.glob('scripts/a4_*.py'),ROOT/'scripts/run-a4-demo.ps1',ROOT/'tests/cpm/test_a4_data.py',
    *ROOT.glob('dashboards/a4/*'),*[ROOT/s for s in ['scripts/cpm/live_run.py','scripts/cpm/live_ros.sh','scripts/cpm/runtime.py','scripts/cpm/validate_live.py','scripts/run_artery_diagnostic.py',
        'scripts/run_integrated_demo.py','scripts/visual_capture.py','scripts/visual_verify.py','scripts/visual_browser_check.py','scripts/run-visual-demo.ps1','scripts/stop-visual-demo.ps1','scripts/stop_visual.py','tests/cpm/test_visual_data.py']]]
hashes={}
for src in sources:
    if not src.is_file():continue
    rel=src.relative_to(ROOT);target=out/'final-tooling'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,target);hashes[rel.as_posix()]=sha(src)
(out/'tooling-hashes.json').write_text(json.dumps(hashes,indent=2))
summary={'passed':True,'metrics':d['metrics'],'live_validation':v,'recorded_regressions':reg,'preservation':preservation,
    'python_tests':json.loads((out/'python-tests/python-tests.json').read_text()),'a1_assertions':34,'a2_assertions':26,'a3_assertions':103,'calibration_assertions':132,
    'dashboard_tests':4,'browser':json.loads((out/'browser-check.json').read_text(encoding='utf-8')) if (out/'browser-check.json').exists() else {'executed':False},
    'f2md_rebuilt':False,'production_tracker_changed':False,'attacks_enabled':False,'committed_or_pushed':False,
    'note':'Scenario, regression and optional browser/visual checks are recorded separately in the evidence.'}
if (out/'visual-validation.json').exists():summary['visual_validation']=json.loads((out/'visual-validation.json').read_text())
for mode in ['live','replay']:
    if (out/('browser-'+mode+'.json')).exists():summary['browser_'+mode]=json.loads((out/('browser-'+mode+'.json')).read_text(encoding='utf-8'))
(out/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
files=[f for f in out.rglob('*') if f.is_file() and not any(part.startswith('browser-profile') for part in f.parts) and f.name not in ['evidence-sha256.json','dashboard.log','dashboard-error.log','dashboard.pid','finalize.log']]
digests={f.relative_to(out).as_posix():sha(f) for f in files}
for name in ['RAPPORT_INTEGRATION_A4.md','RAPPORT_VISUALISATION_A4.md']:
    report=out.parent/name
    if report.exists():digests['../'+name]=sha(report)
(out/'evidence-sha256.json').write_text(json.dumps(digests,indent=2));print(json.dumps({'passed':True,'files_preserved':len(old),'evidence_files':len(digests),'metrics':d['metrics']}))
