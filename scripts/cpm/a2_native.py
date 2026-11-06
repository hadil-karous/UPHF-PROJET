"""Dedicated Artery/SUMO radio replay into the explicitly loaded F2MD service.
No CARLA, ROS, local F2MD TX, attacker roles, AddObj or DropObj.
"""
import datetime,hashlib,json,os,pathlib,shutil,subprocess,time
case=pathlib.Path(os.environ['EXFMD_A2_CASE']); build=case/'build'
assert json.loads((build/'unit-tests.json').read_text())['passed']
assert json.loads((case/'recorded/summary.json').read_text())['converted']==76
out=case/('native-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')); out.mkdir(exist_ok=False)
base=pathlib.Path('/repo/results/integrated/run-20261105-151425')
for name in ['gyrovia.sumocfg','hero.rou.xml']: shutil.copyfile(base/name,out/name)
config=(base/'diagnostic.ini').read_text().replace('--num-clients 2','--num-clients 1').replace('sim-time-limit = 4s','sim-time-limit = 1.5s')
config=config.replace('*.node*.middleware.services = xmldoc("services.xml")',
    '*.node0.middleware.services = xmldoc("sender.xml")\n*.node*.middleware.services = xmldoc("receiver.xml")')
config+='''
**.F2MD_CPService.CP_LOCAL_ATTACKER_PROB = 0
**.F2MD_CPService.CP_LOCAL_ATTACK_TYPE = 0
**.F2MD_CPService.MixCpLocalAttacks = false
**.F2MD_CPService.RandomCpLocalMix = false
**.F2MD_CPService.EnablePC = false
'''
(out/'diagnostic.ini').write_text(config)
(out/'sender.xml').write_text('<services><service type="A2ReplayService"><listener port="2009"/></service></services>')
(out/'receiver.xml').write_text('<services><service type="artery.application.F2MD.F2MD_CPService"><listener port="2009"/></service></services>')
(out/'services-rsu.xml').write_text('<services/>')
(out/'ned').mkdir(); shutil.copyfile('/repo/artery-services/F2MD/A2ReplayService.ned',out/'ned/A2ReplayService.ned')
for directory in ['omnet-results','output/Log','output/GENUINE/CPM/RX','output/GENUINE/CPM/TX','output/GENUINE/LP','output/ATTACK/CPM/Report']: (out/directory).mkdir(parents=True,exist_ok=True)
core=pathlib.Path('/repo/results/phase1/a1-e2e-20261106-161848/build/libartery_core.so')
env=dict(os.environ,EXFMD_A2_REPLAY=str(case/'replay-index.json'),EXFMD_F2MD_RX_ONLY='1',EXFMD_A2_DIR=str(out/'events'),
    LD_LIBRARY_PATH=str(build)+':'+str(core.parent)+':/omnetpp/lib:'+os.environ.get('LD_LIBRARY_PATH',''))
libs=[str(build/'libartery_F2MD.so'),'/artery/build/src/artery/envmod/libartery_envmod.so',str(core),
    '/artery/build/src/traci/libtraci.so','/artery/build/extern/libveins.so','/artery/extern/inet/out/gcc-release/src/libINET.so']
cmd=['/omnetpp/bin/opp_run','-u','Cmdenv','-n',str(out/'ned')+':/artery/src:/artery/extern/veins/src/veins:/artery/extern/inet/src']+['-l'+p for p in libs]+['-f','diagnostic.ini']
with (out/'artery.log').open('w') as log:
    process=subprocess.Popen(cmd,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT)
    maps=''
    for _ in range(200):
        try: maps=pathlib.Path('/proc/'+str(process.pid)+'/maps').read_text()
        except FileNotFoundError: break
        if str(build/'libartery_F2MD.so') in maps:
            (out/'memory-maps.txt').write_text(maps); break
        time.sleep(.005)
    try: code=process.wait(timeout=45)
    except subprocess.TimeoutExpired:
        process.terminate(); process.wait(timeout=10); code='timeout'
events=[]
for p in (out/'events').glob('*.jsonl'): events.extend(json.loads(line) for line in p.read_text().splitlines())
stages={s:sum(e['stage']==s for e in events) for s in ['receive','decode','convert','control','non_evaluable']}
errors=[e for e in events if e['status']=='error']; rejected=[e for e in events if e['stage']=='convert' and e['status']!='ok']
control=[e for e in events if e['stage']=='control']; evaluated=sum(len(e['checks']['evaluated']) for e in control)
anomalies=sum(e['checks']['anomalies'] for e in control)
expected={pathlib.Path(p).read_bytes().hex() for p in json.loads((case/'replay-index.json').read_text())}
decoded=[e for e in events if e['stage']=='decode']; observed={e['source_r2_hex'] for e in decoded}
log=(out/'artery.log').read_text(); tx=log.count('A2_REPLAY_TX ')
summary={'exit_code':code,'transmitted':tx,'receiver_count':len(list((out/'events').glob('*.jsonl'))),
    'stages':stages,'technical_errors':errors,'rejected_conversions':rejected,
    'evaluated_speed_checks':evaluated,'messages_non_evaluable':sum(e['status']=='non_evaluable' for e in control),
    'anomalies':anomalies,'input_payloads_exact':expected==observed,'local_attacker_logged':'Node mbType=LocalAttacker' in log,
    'alert_files':len(list((out/'output').rglob('alert_*.json'))),
    'patched_f2md_loaded':str(build/'libartery_F2MD.so') in maps,
    'original_f2md_loaded':'/artery/build/src/artery/application/F2MD/libartery_F2MD.so' in maps}
(out/'result.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({'output':str(out),**summary},indent=2))
assert code==0 and tx==10 and expected==observed and summary['receiver_count']==2
assert not errors and not rejected and anomalies==0 and evaluated>0 and summary['messages_non_evaluable']>0
assert summary['patched_f2md_loaded'] and not summary['original_f2md_loaded'] and not summary['local_attacker_logged']
