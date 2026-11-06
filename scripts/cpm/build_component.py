"""Run inside the isolated image; compile one object and relink with image objects.
All new build products stay on the D: bind mount. No original image file changes.
"""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import os

root = Path('/artery/build')
out = Path(os.environ.get('EXFMD_CPM_BUILD_DIR','/evidence/corrections'))
out.mkdir(parents=True,exist_ok=True)
flags = (root/'CMakeFiles/core.dir/flags.make').read_text()
args = []
for line in flags.splitlines():
    if line.startswith(('CXX_DEFINES =','CXX_INCLUDES =','CXX_FLAGS =')):
        args.extend(shlex.split(line.split('=',1)[1]))
original = root/'libartery_core.so'
digest = hashlib.sha256(original.read_bytes()).hexdigest()
command = ['g++-10'] + args + ['-c','/repo/artery-services/CarlaPerceptionService.cc',
    '-o',str(out/'CarlaPerceptionService.cc.o')]
subprocess.run(command,check=True)
link = shlex.split((root/'CMakeFiles/core.dir/link.txt').read_text())
link[link.index('-o')+1] = str(out/'libartery_core.so')
old = 'CMakeFiles/core.dir/src/artery/application/CarlaPerceptionService.cc.o'
assert link.count(old) == 1
link[link.index(old)] = str(out/'CarlaPerceptionService.cc.o')
subprocess.run(link,cwd=root,check=True)
assert digest == hashlib.sha256(original.read_bytes()).hexdigest()
(out/'component-build.json').write_text(json.dumps({'compile':command,'link':link,
    'original_core_sha256':digest,'original_unchanged':True,
    'source_hashes': {str(p.relative_to('/repo')): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [Path('/repo/artery-services/CarlaPerceptionService.cc'),
                  Path('/repo/artery-services/CarlaPerceptionService.h'),
                  Path('/repo/artery-services/cpm/PerceptionCpm.h')]},
    'patched_core_sha256':hashlib.sha256((out/'libartery_core.so').read_bytes()).hexdigest()},indent=2))
print('Compiled only CarlaPerceptionService.cc and relinked isolated core; original unchanged.')
