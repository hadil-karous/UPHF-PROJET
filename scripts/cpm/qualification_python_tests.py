"""Run original A1 Python regression tests and the new diagnostic/state tests."""
import json,pathlib,sys,unittest
root=pathlib.Path(__file__).resolve().parents[2]; out=root/sys.argv[1]; out.mkdir(exist_ok=False)
sys.path.insert(0,str(root/'scripts'))
loader=unittest.TestLoader(); suite=unittest.TestSuite()
for pattern in ['test_perception_contract.py','test_estimation_quality.py']:
    suite.addTests(loader.discover(str(root/'tests/cpm'),pattern=pattern))
with (out/'python-tests.log').open('w',encoding='utf-8') as log:
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
summary={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'passed':result.wasSuccessful()}
(out/'python-tests.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary))
raise SystemExit(0 if summary['passed'] else 1)
