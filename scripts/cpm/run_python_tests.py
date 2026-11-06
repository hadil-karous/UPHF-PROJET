import json
from pathlib import Path
import sys
import unittest
import os

root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'scripts'))
suite=unittest.defaultTestLoader.discover(str(root/'tests/cpm'),pattern='test_perception_contract.py')
result=unittest.TextTestRunner(stream=sys.stdout,verbosity=2).run(suite)
out=Path(os.environ.get('EXFMD_CPM_TEST_DIR',str(root/'results/phase1/corrections')))
out.mkdir(parents=True,exist_ok=True)
(out/'python-tests.json').write_text(json.dumps({'tests':result.testsRun,
    'failures':len(result.failures),'errors':len(result.errors),'passed':result.wasSuccessful()},indent=2),encoding='utf-8')
raise SystemExit(0 if result.wasSuccessful() else 1)
