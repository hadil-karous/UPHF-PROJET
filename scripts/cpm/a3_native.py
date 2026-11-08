"""Native Artery/SUMO replay of all original A1 R2 messages; no CARLA/ROS/attacks."""
import collections,datetime,hashlib,json,math,os,pathlib,shutil,subprocess,time
case=pathlib.Path(os.environ['EXFMD_A3_CASE']); root=pathlib.Path('/repo')
build=pathlib.Path(os.environ.get('EXFMD_A3_REPLAY_BUILD',str(case/'build')))
assert json.loads((build/'test_a3.json').read_text())['passed']
recorded=case/(case/'recorded-latest.txt').read_text().strip()
assert json.loads((recorded/'summary.json').read_text())['passed']
out=case/('native-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')); out.mkdir(exist_ok=False)
base=root/'results/integrated/run-20261105-151425'
for name in ['gyrovia.sumocfg','hero.rou.xml']: shutil.copyfile(base/name,out/name)
config=(base/'diagnostic.ini').read_text().replace('--num-clients 2','--num-clients 1').replace('sim-time-limit = 4s','sim-time-limit = 4.5s')
config=config.replace('*.node*.middleware.services = xmldoc("services.xml")',
    '*.node0.middleware.services = xmldoc("sender.xml")\n*.node*.middleware.services = xmldoc("receiver.xml")')
config+='''
**.F2MD_CPService.CP_LOCAL_ATTACKER_PROB = 0
**.F2MD_CPService.CP_LOCAL_ATTACK_TYPE = 0
**.F2MD_CPService.MixCpLocalAttacks = false
**.F2MD_CPService.RandomCpLocalMix = false
**.F2MD_CPService.EnablePC = false
'''
requested={}
if os.environ.get('EXFMD_A3_NED_POLICY'):
    requested=json.loads(pathlib.Path(os.environ['EXFMD_A3_NED_POLICY']).read_text())
    names={'acceleration_m_s2':'MAX_PLAUSIBLE_ACCEL','deceleration_m_s2':'MAX_PLAUSIBLE_DECEL',
        'angular_rate_deg_s':'MAX_PLAUSIBLE_ANGLE_CHANGE','excess_speed_m_s':'TOLERANCE_EXCEED_SPEED'}
    assert set(requested)==set(names), 'Only the four temporal policy parameters can be configured here'
    for key,value in requested.items():
        assert isinstance(value,(int,float)) and math.isfinite(value) and value>=0
        config+='\n**.F2MD_CPService.'+names[key]+' = '+str(value)+'\n'
(out/'diagnostic.ini').write_text(config)
(out/'sender.xml').write_text('<services><service type="A3ReplayService"><listener port="2009"/></service></services>')
(out/'receiver.xml').write_text('<services><service type="artery.application.F2MD.F2MD_CPService"><listener port="2009"/></service></services>')
(out/'services-rsu.xml').write_text('<services/>')
(out/'ned').mkdir(); shutil.copyfile(root/'artery-services/F2MD/A3ReplayService.ned',out/'ned/A3ReplayService.ned')
for directory in ['omnet-results','output/Log','output/GENUINE/CPM/RX','output/GENUINE/CPM/TX','output/GENUINE/LP','output/ATTACK/CPM/Report']:
    (out/directory).mkdir(parents=True,exist_ok=True)
core=root/'results/phase1/a1-e2e-20261106-161848/build/libartery_core.so'
env=dict(os.environ,EXFMD_A3_REPLAY=str(case/'replay-index.json'),EXFMD_F2MD_RX_ONLY='1',EXFMD_A3_TEMPORAL='1',
    EXFMD_A3_DIR=str(out/'events'),LD_LIBRARY_PATH=str(build)+':'+str(core.parent)+':/omnetpp/lib:'+os.environ.get('LD_LIBRARY_PATH',''))
libs=[str(build/'libartery_F2MD.so'),'/artery/build/src/artery/envmod/libartery_envmod.so',str(core),
    '/artery/build/src/traci/libtraci.so','/artery/build/extern/libveins.so','/artery/extern/inet/out/gcc-release/src/libINET.so']
cmd=['/omnetpp/bin/opp_run','-u','Cmdenv','-n',str(out/'ned')+':/artery/src:/artery/extern/veins/src/veins:/artery/extern/inet/src']+['-l'+p for p in libs]+['-f','diagnostic.ini']
wall_timeout=float(os.environ.get('EXFMD_A3_WALL_TIMEOUT','60'))
assert math.isfinite(wall_timeout) and 0<wall_timeout<=180
start=time.monotonic(); maps=''
with (out/'artery.log').open('w') as log:
    process=subprocess.Popen(cmd,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT)
    for _ in range(200):
        try: maps=pathlib.Path('/proc/'+str(process.pid)+'/maps').read_text()
        except FileNotFoundError: break
        if str(build/'libartery_F2MD.so') in maps:
            (out/'memory-maps.txt').write_text(maps); break
        time.sleep(.005)
    try: code=process.wait(timeout=wall_timeout)
    except subprocess.TimeoutExpired:
        process.terminate()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=10)
        code='timeout'
duration=time.monotonic()-start
events=[]
for p in (out/'events').glob('*.jsonl'): events.extend(json.loads(line) for line in p.read_text().splitlines())
controls=[e for e in events if e['stage']=='control' and 'checks' in e]
counts=collections.Counter((r['check'],r['status']) for c in controls for r in c['checks']['checks'])
errors=[e for e in events if e['status'] in ['error','technical_error']]
rejected=[e for e in events if e['stage']=='convert' and e['status']!='ok']
expected={e['sha256'] for e in json.loads((case/'replay-index.json').read_text())}
decoded=[e for e in events if e['stage']=='decode' and e['status']=='ok']
observed={hashlib.sha256(bytes.fromhex(e['source_r2_hex'])).hexdigest() for e in decoded}
log=(out/'artery.log').read_text(); tx=log.count('A3_REPLAY_TX ')
summary={'exit_code':code,'wall_seconds':duration,'simulation_seconds':4.5,'transmitted':tx,
    'wall_timeout_seconds':wall_timeout,
    'requested_temporal_policy':requested,
    'receiver_count':len(list((out/'events').glob('*.jsonl'))),'received':sum(e['stage']=='receive' for e in events),
    'decoded':len(decoded),'converted':sum(e['stage']=='convert' and e['status']=='ok' for e in events),
    'controlled':len(controls),'facility_calls':sum(e['facility_called'] for e in controls),
    'temporal_calls':sum(e['temporal_checks_called'] for e in controls),
    'technical_errors':errors,'rejected_conversions':rejected,'input_payloads_exact':expected==observed,
    'checks':[{'check':k[0],'status':k[1],'count':v} for k,v in sorted(counts.items())],
    'history_actions':dict(collections.Counter(r['history_action'] for c in controls for r in c['checks']['history'])),
    'patched_f2md_loaded':str(build/'libartery_F2MD.so') in maps,
    'original_f2md_loaded':'/artery/build/src/artery/application/F2MD/libartery_F2MD.so' in maps,
    'local_attacker_logged':'Node mbType=LocalAttacker' in log,'genuine_prob0_roles':log.count('Node mbType=Genuine prob=0'),
    'command':cmd,'patched_f2md_sha256':hashlib.sha256((build/'libartery_F2MD.so').read_bytes()).hexdigest()}
(out/'result.json').write_text(json.dumps(summary,indent=2)); print(json.dumps({'output':str(out),**summary},indent=2))
assert code==0 and tx==38 and expected==observed and summary['receiver_count']==2
assert summary['received']==76 and len(controls)==76 and summary['facility_calls']==76 and summary['temporal_calls']==76
assert not errors and not rejected and summary['genuine_prob0_roles']==2 and not summary['local_attacker_logged']
assert summary['patched_f2md_loaded'] and not summary['original_f2md_loaded']
for c in controls:
    for key,value in requested.items(): assert c['checks']['policy'][key]==value, 'F2MD ignored explicit temporal policy: '+key
