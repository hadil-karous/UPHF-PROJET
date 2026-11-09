"""Optional real Edge/Chromium smoke test and screenshot (local websocket-client)."""
import argparse,base64,json,pathlib,subprocess,time,urllib.request
import websocket
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--port',type=int,default=8766);p.add_argument('--browser');a=p.parse_args()
out=pathlib.Path(a.source);profile=out/('browser-profile-'+str(time.time_ns()))
browser=pathlib.Path(a.browser or 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
proc=subprocess.Popen([str(browser),'--headless=new','--disable-gpu','--no-proxy-server','--disable-extensions','--disable-background-networking','--no-first-run','--no-default-browser-check',
    '--remote-debugging-port=0','--remote-allow-origins=*','--user-data-dir='+str(profile.resolve()),'about:blank'],
    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
ws=None;serial=0;runtime_errors=[]
try:
    for _ in range(100):
        f=profile/'DevToolsActivePort'
        try:
            if f.exists():debug=int(f.read_text().splitlines()[0]);break
        except (OSError,ValueError,IndexError):pass
        if proc.poll() is not None:raise RuntimeError('Headless Edge exited')
        time.sleep(.1)
    tabs=json.load(urllib.request.urlopen('http://127.0.0.1:'+str(debug)+'/json'))
    ws=websocket.create_connection(next(t['webSocketDebuggerUrl'] for t in tabs if t['type']=='page'),timeout=45)
    def call(method,params=None):
        global serial
        serial+=1;ws.send(json.dumps({'id':serial,'method':method,'params':params or {}}))
        while True:
            r=json.loads(ws.recv())
            if r.get('method')=='Runtime.exceptionThrown':runtime_errors.append(r)
            if r.get('id')==serial:
                assert 'error' not in r,r
                return r.get('result',{})
    def evaluate(expression):
        r=call('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True})
        assert 'exceptionDetails' not in r,r
        return r.get('result',{}).get('value')
    call('Runtime.enable');call('Page.enable');call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1100,'deviceScaleFactor':1,'mobile':False})
    call('Page.navigate',{'url':'http://127.0.0.1:'+str(a.port)+'/'})
    for _ in range(100):
        ready=evaluate('document.body?.dataset.ready')
        if ready=='true':break
        if ready=='error':raise RuntimeError(evaluate('document.getElementById("error").textContent'))
        time.sleep(.1)
    assert ready=='true'
    result=evaluate('''(()=>{const frames=data.objects;const anomaly=data.object_checks.find(c=>c.status==='anomaly');const selectedId=anomaly?.id??1;
      const index=frames.findIndex(f=>f.frame_id===(anomaly?.frame_id??data.object_checks.find(c=>c.id===selectedId).frame_id));
      document.getElementById('object').value=selectedId;document.getElementById('scrub').value=index;draw();
      return {mode:document.getElementById('mode').textContent,title:document.title,
        object_options:document.getElementById('object').options.length,selected_frame:frames[index].frame_id,
        details:document.getElementById('details').textContent,check_rows:document.getElementById('checks').rows.length,
        selected_checks:JSON.parse(document.getElementById('raw').textContent).length,
        metrics:data.metrics,error:document.getElementById('error').textContent,
        horizontal_overflow:document.documentElement.scrollWidth>window.innerWidth};})()''')
    assert result['object_options']>=2 and result['selected_checks']>0 and not result['error'] and not runtime_errors and not result['horizontal_overflow']
    png=call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
    (out/'dashboard-a4.png').write_bytes(base64.b64decode(png['data']))
    size=call('Page.getLayoutMetrics')['cssContentSize']
    full=call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True,'clip':{'x':0,'y':0,'width':size['width'],'height':size['height'],'scale':1}})
    (out/'dashboard-a4-complet.png').write_bytes(base64.b64decode(full['data']))
    # Verify playback actually advances the selected frame, then stop it.
    evaluate("document.getElementById('play').click()")
    time.sleep(.35)
    result['playback_frame']=evaluate("data.objects[+document.getElementById('scrub').value].frame_id")
    evaluate("document.getElementById('play').click()")
    assert result['playback_frame']!=result['selected_frame']
    result.update(passed=True,runtime_errors=runtime_errors)
    (out/'browser-check.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
finally:
    if ws:
        try:ws.send(json.dumps({'id':99999,'method':'Browser.close'}));ws.close()
        except Exception:pass
    try:proc.wait(timeout=10)
    except subprocess.TimeoutExpired:proc.terminate();proc.wait(timeout=10)
