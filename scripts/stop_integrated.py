"""Stop only this project's diagnostic processes, leaving all other workloads intact."""
import os,signal,pathlib
for entry in os.listdir('/proc'):
 if not entry.isdigit() or int(entry)==os.getpid():continue
 try:
  cmd=pathlib.Path('/proc',entry,'cmdline').read_bytes().split(b'\0')
  owned=b'/repo/scripts/run_integrated_demo.py' in cmd
  if b'/omnetpp/bin/opp_run' in cmd and b'diagnostic.ini' in cmd:
   owned=str(pathlib.Path('/proc',entry,'cwd').resolve()).startswith('/repo/results/integrated/')
  if owned:os.kill(int(entry),signal.SIGTERM);print('Stop requested:',entry)
 except (FileNotFoundError,ProcessLookupError,PermissionError):pass
