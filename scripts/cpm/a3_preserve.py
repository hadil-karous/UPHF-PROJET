"""Hash only existing evidence/results; never write into A1/A2 directories."""
import hashlib,json,pathlib,sys
root=pathlib.Path(__file__).resolve().parents[2]
case=root/sys.argv[1]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
if sys.argv[2]=='before':
    files=set()
    for parent in [root/'results/phase1',root/'results/integrated',root/'results/f2md-probe']:
        if parent.exists(): files.update(p for p in parent.rglob('*') if p.is_file())
    files.update(root.glob('results/RAPPORT*.md'))
    records={str(p.relative_to(root)):sha(p) for p in sorted(files)}
    (case/'preservation-before.json').write_text(json.dumps(records,indent=2))
    print('Saved %d existing evidence fingerprints'%len(records))
else:
    records=json.loads((case/'preservation-before.json').read_text())
    changed=[p for p,h in records.items() if not (root/p).is_file() or sha(root/p)!=h]
    (case/'preservation-after.json').write_text(json.dumps({'files_checked':len(records),'changed':changed,'passed':not changed},indent=2))
    assert not changed, changed
    print('Preserved %d existing evidence files'%len(records))
