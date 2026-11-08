"""Freeze/verify all old phase1/phase3 and historical detection evidence."""
import hashlib,json,pathlib,sys
root=pathlib.Path(__file__).resolve().parents[2]; case=(root/sys.argv[1]).resolve()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
if sys.argv[2]=='before':
    files=[]
    for relative in ['results/phase1','results/phase3','results/integrated','results/f2md-probe']:
        parent=root/relative
        if parent.exists(): files.extend(p for p in parent.rglob('*') if p.is_file() and case not in p.resolve().parents)
    files.extend(root.glob('results/RAPPORT*.md'))
    (case/'preservation-before.json').write_text(json.dumps({str(p.relative_to(root)):sha(p) for p in sorted(set(files))},indent=2))
else:
    old=json.loads((case/'preservation-before.json').read_text())
    changed=[s for s,h in old.items() if not (root/s).is_file() or sha(root/s)!=h]
    (case/'preservation-after.json').write_text(json.dumps({'passed':not changed,'files_checked':len(old),'changed':changed},indent=2))
    assert not changed, changed
    print('Preserved %d files'%len(old))
