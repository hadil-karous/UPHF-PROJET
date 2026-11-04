"""F2MD compatibility probe using a recorded real perception/state snapshot.
This is an offline replay diagnostic, not another live CARLA run.
"""
import pathlib,subprocess,configparser,shutil,json
base=pathlib.Path('/repo/results/integrated/demo-003');out=pathlib.Path('/repo/results/f2md-probe');
if out.exists(): out=out.with_name(out.name+'-'+__import__('datetime').datetime.now().strftime('%Y%m%d-%H%M%S'))
out.mkdir(exist_ok=False)
for name in ['gyrovia.sumocfg','hero.rou.xml','services.xml','services-rsu.xml']:shutil.copyfile(base/name,out/name)
for path in pathlib.Path('/dev/shm').glob('agent_*'):shutil.copyfile(path,out/path.name)
if pathlib.Path('/dev/shm/perceived_0').exists():shutil.copyfile('/dev/shm/perceived_0',out/'perception-snapshot.json')
s=(base/'diagnostic.ini').read_text().replace('--num-clients 2','--num-clients 1').replace('sim-time-limit = 4s','sim-time-limit = 1s')
s+='\n*.node1.middleware.services = xmldoc("services-f2md.xml")\n'
# Put the specific assignment before the wildcard so OMNeT++ selects it.
s=s.replace('*.node*.middleware.services = xmldoc("services.xml")','*.node1.middleware.services = xmldoc("services-f2md.xml")\n*.node*.middleware.services = xmldoc("services.xml")')
s=s[:s.rfind('\n*.node1.middleware.services')]
(out/'probe.ini').write_text(s)
(out/'services-f2md.xml').write_text('''<services><service type="artery.application.CarlaCaService"><listener port="2001"/></service><service type="artery.application.F2MD.F2MD_CPService"><listener port="2009"/></service></services>''')
for path in ['output/Log','output/GENUINE/CPM/RX','output/GENUINE/CPM/TX','output/GENUINE/LP','omnet-results']:(out/path).mkdir(parents=True,exist_ok=True)
cfg=configparser.ConfigParser();cfg.read('/artery/build/run-artery.ini')
cmd=['/omnetpp/bin/opp_run','-u','Cmdenv','-n','/artery/src:/artery/extern/veins/src/veins:/artery/extern/inet/src']+list(dict.fromkeys(cfg['Artery']['libraries'].split()))+['-f','probe.ini']
with (out/'probe.log').open('wb') as log:
 try:r=subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=40);code=r.returncode
 except subprocess.TimeoutExpired:code='timeout'
report={'mode':'offline replay of real final snapshot from demo-003','exit_code':code,'alerts':[str(p.relative_to(out)) for p in out.rglob('alert_*.json')],'outputs':[str(p.relative_to(out)) for p in (out/'output').rglob('*') if p.is_file()]}
(out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));print((out/'probe.log').read_text(errors='replace')[-3500:])
