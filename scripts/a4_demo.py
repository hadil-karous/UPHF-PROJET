"""A4 orchestration: reuse validated binaries; preserve evidence and container states."""
import argparse, datetime, hashlib, json, os, pathlib, socket, subprocess, sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
BUILD='results/phase3/calibration-20261108-190113/build'
NAMES=['exfmd-cpm-a3','exfmd-cpm-a1','exfmd-artery','exfmd-ros','exfmd-carla']
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def docker(*args): return subprocess.check_output(['docker',*args],text=True)
def snapshot(): return json.loads(docker('inspect',*docker('ps','-aq').split()))
def run(cmd,out):
    with out.open('w',encoding='utf-8') as log: subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--case',required=True);p.add_argument('--visual',action='store_true');a=p.parse_args()
    if pathlib.Path(a.case).name!=a.case or not a.case.startswith('a4-'): raise ValueError('Invalid case')
    out=ROOT/'results/phase4'/a.case;out.mkdir(parents=True,exist_ok=False)
    session={'state':'preflight','source':'live_acquisition','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    def state(value,**extra):
        session.update(state=value,**extra);(out/'session.json').write_text(json.dumps(session,indent=2))
    initial=snapshot();(out/'containers-before.json').write_text(json.dumps(initial,indent=2))
    prior={v['Name'].lstrip('/'):v for v in initial}
    for n in NAMES: assert n in prior,'Missing prepared container '+n
    image_ids={n:prior[n]['Image'] for n in NAMES}
    (out/'git-before.txt').write_text(subprocess.check_output(['git','status','--short','--branch'],cwd=ROOT,text=True))
    assert subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='a4-live-integration'
    # All old evidence, production tracker and detector sources are immutable for A4.
    old={}
    for rel in ['results/phase1','results/phase3','results/integrated','results/f2md-probe']:
        for f in (ROOT/rel).rglob('*'):
            if f.is_file(): old[f.relative_to(ROOT).as_posix()]=sha(f)
    for f in (ROOT/'cosimulation/carla_multi_agent').glob('*.py'):old[f.relative_to(ROOT).as_posix()]=sha(f)
    for f in (ROOT/'artery-services').rglob('*'):
        if f.is_file():old[f.relative_to(ROOT).as_posix()]=sha(f)
    # Preserve every frozen A4 artifact too; ignore only its intentionally mutable web logs.
    for manifest_path in (ROOT/'results/phase4').glob('*/evidence-sha256.json'):
        for relative,digest in json.loads(manifest_path.read_text()).items():
            f=(manifest_path.parent/relative).resolve()
            assert sha(f)==digest,'Historical A4 evidence changed: '+str(f)
            old[f.relative_to(ROOT).as_posix()]=digest
    (out/'preservation-before.json').write_text(json.dumps(old,indent=2))
    started=[]
    try:
        if not prior['exfmd-carla']['State']['Running']:
            for port in [2000,2001,2002,8000]:
                with socket.socket() as s: s.bind(('127.0.0.1',port))
        manifest=json.loads((ROOT/BUILD/'manifest.json').read_text())
        for rel,h in manifest['source_hashes'].items():
            content=(ROOT/rel).read_bytes()
            assert sha(ROOT/rel)==h or hashlib.sha256(content.replace(b'\r\n',b'\n')).hexdigest()==h,rel
        assert sha(ROOT/BUILD/'libartery_F2MD.so')=='1d18655c07c943b0514d2453d139eb1b004329edcefe09a3bd05193d5557e229'
        for n in ['exfmd-cpm-a3','exfmd-cpm-a1']:
            if not prior[n]['State']['Running']:docker('start',n);started.append(n)
        run([sys.executable,'scripts/cpm/a34_tests.py',str(out.relative_to(ROOT)/'python-tests')],out/'python-run.log')
        run([sys.executable,'-m','unittest','discover','-s','tests/cpm','-p','test_a4_data.py','-v'],out/'dashboard-tests.log')
        if a.visual:run([sys.executable,'-m','unittest','discover','-s','tests/cpm','-p','test_visual_data.py','-v'],out/'visual-unit-tests.log')
        envlib='/repo/'+BUILD+':/repo/results/phase1/a1-e2e-20261106-161848/build:/omnetpp/lib'
        for name in ['test_a2','test_a3','test_calibration']:
            run(['docker','exec','-e','LD_LIBRARY_PATH='+envlib,'exfmd-cpm-a3','/repo/'+BUILD+'/'+name],out/(name+'.json'))
        state('running');print('A4 live evidence: '+str(out),flush=True)
        # live_run starts only these prepared runtime containers, in IPC dependency order.
        for n in ['exfmd-artery','exfmd-ros','exfmd-carla']:
            if not prior[n]['State']['Running']:started.append(n)
        run([sys.executable,'scripts/cpm/live_run.py','--case',a.case,'--phase','phase4','--f2md']+(['--visual'] if a.visual else []),out/'live-run.log')
        state('validating')
        attempt=out/'attempt-01'
        run([sys.executable,'scripts/cpm/validate_live.py','--attempt',str(attempt),'--f2md'],out/'perception-validation.log')
        (out/'a1-regression').mkdir(exist_ok=True)
        run(['docker','exec','exfmd-artery','/repo/results/phase1/corrections/test_cpm',
            '/repo/'+(out.relative_to(ROOT)/'a1-regression').as_posix()],out/'a1-regression.log')
        run([sys.executable,'scripts/a4_validate.py','--attempt',str(attempt)],out/'f2md-validation.log')
        run([sys.executable,'scripts/a4_regressions.py','--source',str(out)],out/'recorded-regressions.log')
        if a.visual:run([sys.executable,'scripts/visual_verify.py','--source',str(out)],out/'visual-verify.log')
        state('completed',passed=True)
    except BaseException as e:
        state('failed',passed=False,error=repr(e));raise
    finally:
        cleanup=[]
        for n in reversed(started):
            r=subprocess.run(['docker','stop',n],capture_output=True,text=True)
            cleanup.append({'container':n,'exit_code':r.returncode,'stderr':r.stderr})
        after=snapshot();(out/'containers-after.json').write_text(json.dumps(after,indent=2))
        post={v['Name'].lstrip('/'):v for v in after}
        changed=[rel for rel,h in old.items() if not (ROOT/rel).is_file() or sha(ROOT/rel)!=h]
        containers={n:post[n]['Id']==v['Id'] and post[n]['Image']==v['Image'] and post[n]['State']['Running']==v['State']['Running'] for n,v in prior.items()}
        images={n:docker('image','inspect',v,'--format','{{.Id}}').strip()==v for n,v in image_ids.items()}
        preservation={'files_checked':len(old),'changed':changed,'containers':containers,'images':images,'cleanup':cleanup}
        preservation['passed']=not changed and all(containers.values()) and all(images.values()) and all(x['exit_code']==0 for x in cleanup)
        (out/'preservation-after.json').write_text(json.dumps(preservation,indent=2))
        if not preservation['passed']:state('failed',passed=False,error='preservation verification failed')
        assert preservation['passed'],preservation
    try:
        run([sys.executable,'scripts/a4_figures.py','--source',str(out)],out/'figures.log')
        run([sys.executable,'scripts/a4_finalize.py','--source',str(out)],out/'finalize.log')
    except BaseException as e:
        state('failed',passed=False,error=repr(e));raise
    print(str(out),flush=True)
if __name__=='__main__':main()
