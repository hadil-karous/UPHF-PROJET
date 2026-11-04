import configparser, pathlib, subprocess, json, re
out=pathlib.Path('/repo/results/runtime-audit'); out.mkdir(exist_ok=True)
root=pathlib.Path('/artery'); scenario=root/'scenarios/F2MD_Highway_CPM'
for name in ['omnetpp.ini','services.xml','slow.sumo.cfg','slow.rou.xml','run-artery.ini']:
    (out/('original-'+name)).write_bytes((scenario/name).read_bytes())
cfg=configparser.ConfigParser(); cfg.read('/artery/build/run-artery.ini')
cmd=['/omnetpp/bin/opp_run','-u','Cmdenv','-n',cfg['Artery']['nedFolders']]
cmd+=cfg['Artery']['libraries'].split()+['-f',str(scenario/'omnetpp.ini'),'--sim-time-limit=3s','--cmdenv-interactive=false']
try:
    r=subprocess.run(cmd,cwd=scenario,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=45)
    (out/'artery-original.log').write_bytes(r.stdout)
    print(r.stdout.decode(errors='replace')[-6000:]); print('exit',r.returncode)
except subprocess.TimeoutExpired as e:
    (out/'artery-original.log').write_bytes(e.stdout or b''); print('Original launch timed out')
(out/'launch-command.json').write_text(json.dumps(cmd,indent=2))
for name in ['CarlaCaService.cc','CarlaPerceptionService.cc','CarlaPerceptionService.ned']:
    p=root/'src/artery/application'/name
    if p.exists(): (out/name).write_bytes(p.read_bytes())
for name in ['PacketCaptureRequestInterface.h']:
    (out/name).write_bytes((root/'src/artery/networking'/name).read_bytes())
