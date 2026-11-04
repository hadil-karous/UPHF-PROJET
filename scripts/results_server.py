"""Local results viewer: recorded simulation data and independently queried container state."""
import csv,json,pathlib,subprocess,time,os
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
ROOT=pathlib.Path(__file__).resolve().parents[1]/'results'
def dataset():
    runs=[]
    for folder in sorted((ROOT/'integrated').glob('*'),reverse=True) if (ROOT/'integrated').exists() else []:
        if not (folder/'report.json').exists():continue
        report=json.loads((folder/'report.json').read_text(encoding='utf-8-sig'))
        if (folder/'positions.csv').exists():
            rows=list(csv.DictReader((folder/'positions.csv').open()))
        else:rows=[]
        if not rows:continue
        runs.append((folder,report,rows))
    if runs:folder,report,rows=runs[0]
    else:
        folder=ROOT/'scenario2-carla/20261104-183524';report=json.loads((folder/'report.json').read_text());rows=list(csv.DictReader((folder/'positions.csv').open()))
    rel=folder.relative_to(ROOT).as_posix();points=[]
    ply=folder/'lidar.ply'
    if ply.exists():
        text=ply.read_text();points=[[float(v) for v in line.split()[:3]] for line in text.split('end_header\n',1)[1].splitlines() if line.strip()][:20000]
    normalized=[]
    for r in rows:
        normalized.append({'id':r.get('sumo_id','hero'),'x':float(r.get('x',r.get('x_m',0))),'y':float(r.get('y',r.get('y_m',0))),'speed':float(r.get('speed_m_s',0)),'step':int(r.get('step',r.get('frame',0))),'error':float(r.get('sync_position_error_m',0))})
    images={k:'/'+rel+'/'+name for k,name in [('overview','overview.png'),('onboard','onboard.png')] if (folder/name).exists()}
    if not images and (folder/'gyrovia_hero.png').exists():images['overview']='/'+rel+'/gyrovia_hero.png'
    scalars=[]
    for f in (folder/'omnet-results').glob('*.sca') if (folder/'omnet-results').exists() else []:
        for line in f.read_text(errors='replace').splitlines():
            if line.startswith('scalar ') and ('reception:count' in line or 'transmission:count' in line):scalars.append(line)
    f2md_path=ROOT/'f2md-native-probe/report.json'
    f2md=json.loads(f2md_path.read_text()) if f2md_path.exists() else None
    return {'f2md_native':f2md,'run':rel,'recorded':True,'report':report,'rows':normalized,'lidar':points,'images':images,'rsu_scalars':scalars,'files':{'positions':'/'+rel+'/positions.csv','report':'/'+rel+'/report.json','messages':'/'+rel+'/ros-messages.jsonl','artery':'/'+rel+'/artery.log','lidar':'/'+rel+'/lidar.ply'}}
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT),**kwargs)
    def do_GET(self):
        if self.path.split('?')[0] in ['/api/data','/api/status']:
            try:
                if self.path.startswith('/api/data'):data=dataset()
                else:
                    p=subprocess.run(['docker','ps','-a','--format','{{json .}}'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=8,text=True)
                    data={'queried_at':time.time(),'containers':[json.loads(x) for x in p.stdout.splitlines() if json.loads(x)['Names'] in ['exfmd-carla','exfmd-ros','exfmd-artery']],'note':'Ã‰tat des conteneurs uniquement : aucun Ã©change validÃ© par cet Ã©tat.'}
                body=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
            except Exception as e:self.send_error(500,str(e))
        elif self.path=='/':self.send_response(302);self.send_header('Location','/dashboard/');self.end_headers()
        else:super().do_GET()
if __name__=='__main__':
    print('Dashboard: http://127.0.0.1:8765/dashboard/',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
