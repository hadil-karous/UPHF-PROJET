"""Offline-first local A4 viewer, adapted from results_server's stdlib HTTP design."""
import argparse,json,pathlib,re
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from a4_data import dataset
ROOT=pathlib.Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--port',type=int,default=8766);p.add_argument('--live',action='store_true');p.add_argument('--visual',action='store_true');a=p.parse_args()
    source=pathlib.Path(a.source).resolve()
    source.relative_to(ROOT/'results')
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url=self.path.split('?')[0]
            try:
                if url=='/api/data':body=json.dumps(dataset(source,a.live),allow_nan=False).encode();mime='application/json'
                elif url in ['/','/index.html']:body=(ROOT/'dashboards/a4'/('visual.html' if a.visual else 'index.html')).read_bytes();mime='text/html; charset=utf-8'
                elif url=='/app.js':body=(ROOT/'dashboards/a4/app.js').read_bytes();mime='text/javascript; charset=utf-8'
                elif url=='/visual.js':body=(ROOT/'dashboards/a4/visual.js').read_bytes();mime='text/javascript; charset=utf-8'
                elif re.fullmatch(r'/video/(overview|onboard)/[0-9]+\.png',url):
                    folder=source if source.name.startswith('attempt-') else max(source.glob('attempt-*'))
                    _,_,view,filename=url.split('/')
                    body=(folder/'video'/view/('frame-%08d.png'%int(filename[:-4]))).read_bytes();mime='image/png'
                elif url in ['/evidence/overview.png','/evidence/onboard.png']:
                    folder=source if source.name.startswith('attempt-') else max(source.glob('attempt-*'))
                    body=(folder/pathlib.PurePosixPath(url).name).read_bytes();mime='image/png'
                else:self.send_error(404);return
                self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
            except (OSError,ValueError) as e:self.send_error(500,str(e))
    print('A4 dashboard http://127.0.0.1:'+str(a.port),flush=True)
    ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
if __name__=='__main__':main()
