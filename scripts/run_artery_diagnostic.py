import os
"""Explicit diagnostic derivative, using shipped Gyrovia network and Artery services."""
import pathlib, xml.etree.ElementTree as ET, configparser, subprocess, os, sys, copy, json
from cpm.runtime import validated_core
core=validated_core()
out=pathlib.Path(os.environ.get('EXFMD_OUTPUT_DIR',str(pathlib.Path('/repo/results/integrated')/os.environ.get('EXFMD_RUN','demo-002')))); out.mkdir(parents=True,exist_ok=True)
# Archive and clear only the project's own shared state, so a fresh run cannot emit stale perception.
prior=out/'prior-shm';prior.mkdir(exist_ok=True)
for idx in range(3):
    for stem in ['agent_','perceived_']:
        state=pathlib.Path('/dev/shm')/(stem+str(idx))
        if state.exists(): (prior/state.name).write_bytes(state.read_bytes())
    (pathlib.Path('/dev/shm')/('agent_'+str(idx))).write_bytes(bytes(56))
    (pathlib.Path('/dev/shm')/('perceived_'+str(idx))).write_text('{"objects":[],"count":0}')
base=pathlib.Path('/repo/cosimulation/sumo-integration/carla/Co-Simulation/Sumo/examples/uphf_piste')
root=ET.parse(base/'uphf_piste.rou.xml').getroot(); routes=ET.Element('routes')
ET.SubElement(routes,'vType',id='vehicle.tesla.model3',accel='1.5',decel='4.5',length='4.5',minGap='2',maxSpeed='4')
v=root.find('vehicle'); v.set('id','hero'); v.set('type','vehicle.tesla.model3'); v.set('depart','0'); v.set('departPos','3'); routes.append(v)
for idx in range(1,int(os.environ.get('EXFMD_VEHICLES','1'))):
    other=copy.deepcopy(v); other.set('id','hero'+str(idx)); other.set('departPos',str(3+7*idx));routes.append(other)
ET.ElementTree(routes).write(out/'hero.rou.xml')
(out/'gyrovia.sumocfg').write_text('<configuration><input><net-file value="'+str(base/'uphf_piste.net.xml')+'"/><route-files value="hero.rou.xml"/></input><time><step-length value="0.05"/><end value="5"/></time></configuration>')
# This diagnostic deliberately instantiates no F2MD or attack service.
(out/'services.xml').write_text('''<services>
<service type="artery.application.CarlaCaService"><listener port="2001"/></service>
<service type="artery.application.CamUdpExportService"><listener port="2001"/></service>
<service type="artery.application.CarlaPerceptionService"><listener port="2009"/></service>
</services>''')
(out/'services-rsu.xml').write_text('<services><service type="artery.application.RsuCaService"><listener port="2001"/></service></services>')
(out/'diagnostic.ini').write_text('''[General]
network = artery.envmod.World
sim-time-limit = 4s
cmdenv-express-mode = true
cmdenv-interactive = false
print-undisposed = false
result-dir = omnet-results
**.vector-recording = false
**.scalar-recording = true
*.traci.core.version = -1
*.traci.launcher.typename = "PosixLauncher"
*.traci.launcher.sumo = "/repo/results/runtime-audit/deps/sumo/bin/sumo"
*.traci.launcher.sumocfg = "gyrovia.sumocfg"
*.traci.launcher.port = 8813
*.traci.launcher.extraOptions = "--num-clients 2 --step-length 0.05"
*.traci.mapper.vehicleType = "artery.envmod.Car"
**.identityRegistryModule = "idRegistry"
*.withPhysicalEnvironment = false
*.node*.environmentModel.sensors = xml("<sensors/>")
*.node*.middleware.datetime = "2018-03-19 10:00:00"
*.node*.middleware.updateInterval = 0.1s
*.node*.middleware.services = xmldoc("services.xml")
*.node*.middleware.CarlaCaService.maxInterval = 0.1s
*.node*.middleware.CarlaPerceptionService.maxInterval = 0.1s
*.node*.middleware.CarlaPerceptionService.fixedRate = true
*.numRoadSideUnits = 1
*.rsu[0].mobility.initialX = 95m
*.rsu[0].mobility.initialY = 45m
*.rsu[0].mobility.initialZ = 3m
*.rsu[*].middleware.datetime = "2018-03-19 10:00:00"
*.rsu[*].middleware.services = xmldoc("services-rsu.xml")
*.rsu[*].middleware.RsuCaService.reception.result-recording-modes = count
*.rsu[*].middleware.RsuCaService.transmission.result-recording-modes = count
''')
(out/'omnet-results').mkdir(exist_ok=True)
cfg=configparser.ConfigParser(); cfg.read('/artery/build/run-artery.ini')
libraries=['-l/artery/build/extern/libveins.so','-l/artery/extern/inet/out/gcc-release/src/libINET.so',
    '-l/artery/build/src/traci/libtraci.so','-l/artery/build/src/artery/envmod/libartery_envmod.so','-l'+str(core)]
cmd=['/omnetpp/bin/opp_run','-u','Cmdenv','-n','/artery/src:/artery/extern/veins/src/veins:/artery/extern/inet/src']+list(dict.fromkeys(libraries))+['-f','diagnostic.ini']
os.environ['LD_LIBRARY_PATH']=str(core.parent)+':'+os.environ.get('LD_LIBRARY_PATH','')
print('Diagnostic Gyrovia derivative, not the original highway scenario',flush=True)
process=subprocess.Popen(cmd,cwd=out)
(out/'artery-process.json').write_text(json.dumps({'pid':process.pid,'command':cmd,'core':str(core)},indent=2))
raise SystemExit(process.wait())
