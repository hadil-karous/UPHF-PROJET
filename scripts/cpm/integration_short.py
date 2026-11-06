"""Short native Artery/SUMO integration, only after unit tests.
Uses a known JSON v2 fixture, no CARLA and no F2MD/attack service.
"""
import datetime
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import argparse

out=Path('/evidence/corrections')
parser=argparse.ArgumentParser(); parser.add_argument('--baseline',action='store_true')
baseline=parser.parse_args().baseline
assert json.loads((out/'cpp-tests.json').read_text())['passed']
case=out/(('baseline-' if baseline else 'integration-')+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
case.mkdir(exist_ok=False)
base=Path('/repo/results/integrated/run-20261105-151425')
for name in ['gyrovia.sumocfg','hero.rou.xml','services.xml','services-rsu.xml']:
    shutil.copyfile(base/name,case/name)
config=(base/'diagnostic.ini').read_text().replace('--num-clients 2','--num-clients 1').replace('sim-time-limit = 4s','sim-time-limit = 0.7s')
(case/'diagnostic.ini').write_text(config)
for i in range(3):
    fixture=json.loads((out/'fixture-v2.json').read_text())
    # Same fixture in both runs; aliases permit the original regex reader to
    # receive its old GPS fields. The v2 builder ignores these legacy aliases.
    fixture.update(ref_lat=fixture['reference']['latitude'],ref_lon=fixture['reference']['longitude'],ref_heading=fixture['reference']['heading_deg'])
    text=json.dumps(fixture)
    (case/('perceived_'+str(i))).write_text(text)
    if baseline: Path('/dev/shm/perceived_'+str(i)).write_text(text)
(case/'omnet-results').mkdir()
sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); sock.settimeout(.1); sock.bind(('127.0.0.1',9602))
packets=[]; stop=threading.Event()
def receive():
    while not stop.is_set():
        try: packets.append(sock.recv(65535))
        except socket.timeout: pass
thread=threading.Thread(target=receive); thread.start()
env=dict(os.environ,EXFMD_PERCEPTION_DIR=str(case),LD_LIBRARY_PATH=('' if baseline else str(out)+':')+'/omnetpp/lib:'+os.environ.get('LD_LIBRARY_PATH',''))
libs=['/artery/build/extern/libveins.so','/artery/extern/inet/out/gcc-release/src/libINET.so',
      '/artery/build/src/traci/libtraci.so',
      '/artery/build/src/artery/envmod/libartery_envmod.so',
      '/artery/build/libartery_core.so' if baseline else str(out/'libartery_core.so')]
command=['/omnetpp/bin/opp_run','-u','Cmdenv','-n','/artery/src:/artery/extern/veins/src/veins:/artery/extern/inet/src']+['-l'+lib for lib in libs]+['-f','diagnostic.ini']
try:
    with (case/'artery.log').open('w') as log:
        result=subprocess.run(command,cwd=case,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=45)
finally:
    stop.set(); thread.join(); sock.close()
decoded=[]
for i,packet in enumerate(packets):
    assert int.from_bytes(packet[40:42],'big')==2009
    path=case/('packet-'+str(i)+'.uper'); path.write_bytes(packet[44:])
    check=subprocess.run(['/evidence/decode_cpm','r2',str(path)],capture_output=True,text=True,check=True)
    msg=json.loads(check.stdout); decoded.append(msg)
    assert msg['valid'] and msg['consumed_bytes']==msg['input_bytes']
    if baseline:
        assert [o['id'] for o in msg['objects']]==[1,2]
        assert msg['objects'][0]['vx_m_s']==5 and msg['objects'][0]['vy_m_s']==0
        assert msg['objects'][0]['acceleration_present']
    else:
        assert [o['id'] for o in msg['objects']]==[71,9]
        assert msg['objects'][0]['vx_m_s']==-3 and msg['objects'][0]['vy_m_s']==4
        assert not msg['objects'][0]['acceleration_present']
log=(case/'artery.log').read_text()
summary={'exit_code':result.returncode,'captured_packets':len(packets),'decoded':decoded,
         'baseline_original_core':baseline,
         'r2_rx_logged':'CPM_A1_RX' in log,'tx_logged':'CPM_A1_TX' in log,
         'scope':('Original' if baseline else 'Patched')+' Artery service; frozen fixture; 0.7s SUMO; no CARLA/ROS/F2MD'}
(case/'result.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({'path':str(case),**{k:v for k,v in summary.items() if k!='decoded'}},indent=2))
assert result.returncode==0 and packets
if not baseline: assert summary['r2_rx_logged'] and summary['tx_logged']
