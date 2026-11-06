"""Fail closed rather than combine JSON v2 with an old or stale image core."""
import hashlib
import json
import os
from pathlib import Path


def validated_core(root=Path('/repo')):
    root=Path(root)
    core=Path(os.environ.get('EXFMD_CPM_CORE',str(root/'results/phase1/corrections/libartery_core.so')))
    manifest=core.with_name('component-build.json')
    if not core.is_file() or not manifest.is_file():
        raise RuntimeError('CPM v2 core missing: run scripts/cpm/run-tests.ps1 -Integration first')
    build=json.loads(manifest.read_text())
    for relative, digest in build['source_hashes'].items():
        if hashlib.sha256((root/relative).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('CPM v2 source changed: rebuild before starting Artery')
    if hashlib.sha256(core.read_bytes()).hexdigest()!=build['patched_core_sha256']:
        raise RuntimeError('CPM v2 binary does not match build manifest')
    return core


if __name__=='__main__':
    print(validated_core())
