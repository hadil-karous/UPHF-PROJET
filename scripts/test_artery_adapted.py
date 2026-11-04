import pathlib, configparser, subprocess
out=pathlib.Path('/repo/results/runtime-audit')
s=pathlib.Path('/artery/scenarios/F2MD_Highway_CPM/omnetpp.ini').read_text()
s=s.replace('/home/syfra/artery_fresh','/artery')
s=s.replace('ned-path = ', '# original ned-path = ')
s=s.replace('300**.middleware.datetime = "2018-03-19 10:00:00"','300')
(out/'adapted-original.ini').write_text(s)
cfg=configparser.ConfigParser(); cfg.read('/artery/build/run-artery.ini')
cmd=['/omnetpp/bin/opp_run','-u','Cmdenv','-n','/artery/src:/artery/extern/veins/src/veins:/artery/extern/inet/src']
cmd+=list(dict.fromkeys(cfg['Artery']['libraries'].split()))+['-f',str(out/'adapted-original.ini'),'--sim-time-limit=3s','--cmdenv-interactive=false']
with (out/'artery-adapted.log').open('wb') as log:
    try:
        r=subprocess.run(cmd,cwd='/artery/scenarios/F2MD_Highway_CPM',stdout=log,stderr=subprocess.STDOUT,timeout=25)
        print('exit',r.returncode)
    except subprocess.TimeoutExpired: print('timeout after 25 seconds; see log')
print((out/'artery-adapted.log').read_text(errors='replace')[-6000:])
