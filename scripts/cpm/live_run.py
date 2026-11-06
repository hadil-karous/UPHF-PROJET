"""Run a short real CARLA/SUMO/ROS/Artery scenario and keep every attempt.

Use a pre-built isolated core. No Docker image changes, no F2MD library/service,
no dashboard/current-run changes, no destructive cleanup of prior results.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import time
import shutil

ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser()
parser.add_argument('--case',required=True,help='Existing/new directory name under results/phase1')
args=parser.parse_args()
if Path(args.case).name!=args.case: raise SystemExit('case must be a directory name')
case=ROOT/'results/phase1'/args.case
case.mkdir(exist_ok=True)
attempt=next(case/('attempt-%02d'%i) for i in range(1,100) if not (case/('attempt-%02d'%i)).exists())
attempt.mkdir(exist_ok=False)
sources=['scripts/run_integrated_demo.py','scripts/run_artery_diagnostic.py',
    'cosimulation/carla_multi_agent/fusion_detector.py','cosimulation/carla_multi_agent/vehicle_agent.py',
    'cosimulation/carla_multi_agent/perception_contract.py','artery-services/CarlaPerceptionService.cc',
    'artery-services/CarlaPerceptionService.h','artery-services/cpm/PerceptionCpm.h']
hashes={}
for relative in sources:
    target=attempt/'sources'/relative; target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(ROOT/relative,target)
    hashes[relative]=hashlib.sha256(target.read_bytes()).hexdigest()
(attempt/'source-hashes.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
linux='/repo/results/phase1/'+args.case+'/'+attempt.name
core='/repo/results/phase1/'+args.case+'/build/libartery_core.so'
def docker(*cmd,**kwargs):
    return subprocess.run(['docker',*cmd],text=True,**kwargs)
def capture(*cmd):
    return docker(*cmd,capture_output=True,check=True).stdout
def start(name):
    state=json.loads(capture('inspect',name))[0]
    if not state['State']['Running']: capture('start',name)
initial=[json.loads(x) for x in capture('ps','-a','--format','{{json .}}').splitlines()]
(attempt/'docker-before.json').write_text(json.dumps(initial,indent=2),encoding='utf-8')
for name in ['exfmd-artery','exfmd-ros','exfmd-carla']: start(name)
common=['-e','EXFMD_OUTPUT_DIR='+linux]
for index in range(18):
    probe=docker('exec',*common,'exfmd-ros','bash','/repo/scripts/cpm/live_ros.sh',
        '/repo/scripts/cpm/live_probe.py',capture_output=True,timeout=20)
    (attempt/('preflight-%02d.log'%index)).write_text(probe.stdout+probe.stderr,encoding='utf-8')
    if probe.returncode==0: break
    print('Waiting for CARLA readiness, attempt',index+1,flush=True)
    time.sleep(2)
else: raise SystemExit('CARLA not ready; see preflight logs')
capture('exec','-e','EXFMD_CPM_CORE='+core,'exfmd-artery','python3','/repo/scripts/cpm/runtime.py')
# Refuse another tick owner or a live scenario in the project's own containers.
for container,pattern in [('exfmd-ros','^python3 /repo/scripts/run_integrated_demo.py$'),('exfmd-artery','^/omnetpp/bin/opp_run ' )]:
    running=docker('exec',container,'pgrep','-f',pattern,capture_output=True)
    if running.returncode==0: raise SystemExit('Scenario already running in '+container)
artery_log=(attempt/'artery.log').open('w',encoding='utf-8')
artery=subprocess.Popen(['docker','exec',*common,'-e','EXFMD_CPM_CORE='+core,
    '-e','EXFMD_VEHICLES=3','-e','EXFMD_CPM_TRACE_DIR='+linux+'/cpm-tx',
    'exfmd-artery','python3','/repo/scripts/run_artery_diagnostic.py'],stdout=artery_log,stderr=subprocess.STDOUT)
print('Evidence:',attempt,flush=True)
ros=None
try:
    # Check LISTEN in /proc; never open a spurious TraCI client connection.
    probe="from pathlib import Path; assert any(s[1].endswith(':226D') and s[3]=='0A' for s in (l.split() for l in Path('/proc/net/tcp').read_text().splitlines()[1:]))"
    for _ in range(60):
        if artery.poll() is not None: raise RuntimeError('Artery exited before SUMO readiness')
        ready=docker('exec','exfmd-artery','python3','-c',probe,capture_output=True)
        if ready.returncode==0: break
        time.sleep(.5)
    else: raise RuntimeError('SUMO did not listen on port 8813')
    process=json.loads((attempt/'artery-process.json').read_text())
    maps=capture('exec','exfmd-artery','cat','/proc/'+str(process['pid'])+'/maps')
    (attempt/'artery-memory-maps.txt').write_text(maps,encoding='utf-8')
    assert core in maps and '/artery/build/libartery_core.so' not in maps
    assert 'libartery_F2MD' not in maps
    with (attempt/'ros.log').open('w',encoding='utf-8') as log:
        ros=subprocess.Popen(['docker','exec',*common,'-e','EXFMD_FUSION_TRACE_DIR='+linux+'/fusion',
            'exfmd-ros','bash','/repo/scripts/cpm/live_ros.sh','/repo/scripts/run_integrated_demo.py'],
            stdout=log,stderr=subprocess.STDOUT)
        code=ros.wait(timeout=300)
    artery_code=artery.wait(timeout=20)
    result={'ros_exit_code':code,'artery_exit_code':artery_code,'core':core,
        'f2md_loaded':False,'nominal_steps':75,'nominal_sumo_time_s':3.75}
    (attempt/'execution.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)
    if code or artery_code: raise RuntimeError('Scenario failed; see logs')
finally:
    if ros is not None and ros.poll() is None and (attempt/'running.json').exists():
        pid=json.loads((attempt/'running.json').read_text())['pid']
        docker('exec','exfmd-ros','kill','-TERM',str(pid),capture_output=True)
        try: ros.wait(timeout=15)
        except subprocess.TimeoutExpired:
            docker('exec','exfmd-ros','kill','-KILL',str(pid),capture_output=True)
    # Stop only the exact recorded scenario process, never another container.
    if artery.poll() is None and (attempt/'artery-process.json').exists():
        pid=json.loads((attempt/'artery-process.json').read_text())['pid']
        docker('exec','exfmd-artery','kill','-TERM',str(pid),capture_output=True)
        try: artery.wait(timeout=10)
        except subprocess.TimeoutExpired:
            docker('exec','exfmd-artery','kill','-KILL',str(pid),capture_output=True)
    artery_log.close()
