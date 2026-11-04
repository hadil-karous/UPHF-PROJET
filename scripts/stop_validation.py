import os, signal
for entry in os.listdir('/proc'):
    if not entry.isdigit(): continue
    try:
        cmd = open('/proc/'+entry+'/cmdline','rb').read().split(b'\0')
        if b'/tmp/exfmd-validate.py' in cmd or b'/tmp/exfmd-cosim.py' in cmd:
            os.kill(int(entry), signal.SIGTERM)
            print('Stop requested for validation PID',entry)
    except (FileNotFoundError, ProcessLookupError, PermissionError): pass
