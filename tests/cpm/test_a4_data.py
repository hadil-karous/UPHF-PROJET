"""Evidence semantics: offline, partial writes and native/ROS separation."""
import hashlib,json,os,pathlib,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'scripts'))
from a4_data import dataset,lines
class A4DataTests(unittest.TestCase):
    def test_ros_copies_do_not_count_as_native_rx(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);a=root/'attempt-01';a.mkdir()
            (a/'ros-messages.jsonl').write_text(json.dumps({'topic':'/simulator/vehicle1/cpm'})+'\n')
            d=dataset(root);self.assertEqual(d['metrics']['ros_cpm_copies'],1);self.assertEqual(d['metrics']['radio_rx'],0)
            self.assertIsNone(d['metrics']['vehicles']);self.assertFalse(d['validated'])
    def test_watch_becomes_replay_at_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            (root/'session.json').write_text('{"state":"running"}')
            self.assertEqual(dataset(root,True)['mode'],'live')
            self.assertEqual(dataset(root,False)['mode'],'replay')
            (root/'session.json').write_text('{"state":"failed"}')
            d=dataset(root,True);self.assertEqual(d['mode'],'replay');self.assertFalse(d['validated'])
    def test_partial_tail_is_ignored_but_bad_record_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=pathlib.Path(tmp)/'events.jsonl';f.write_text('{"n":1}\n{"n":')
            self.assertEqual(lines(f),[{'n':1}])
            f.write_text('{broken}\n')
            with self.assertRaises(json.JSONDecodeError):lines(f)
    def test_core_archive_allows_only_verified_line_endings(self):
        from cpm.runtime import validated_core
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);build=root/'build';build.mkdir();archive=root/'archive';archive.mkdir()
            core=build/'libartery_core.so';core.write_bytes(b'unit fixture')
            original=b'one\r\ntwo\n';(archive/'source.cc').write_bytes(original)
            (root/'source.cc').write_bytes(b'one\r\ntwo\r\n')
            (build/'component-build.json').write_text(json.dumps({'source_hashes':{'source.cc':hashlib.sha256(original).hexdigest()},'patched_core_sha256':hashlib.sha256(core.read_bytes()).hexdigest()}))
            with patch.dict(os.environ,{'EXFMD_CPM_CORE':str(core),'EXFMD_CPM_SOURCE_ARCHIVE':str(archive)}):
                self.assertEqual(validated_core(root),core)
                (root/'source.cc').write_bytes(b'one\r\nEDIT\r\n')
                with self.assertRaises(RuntimeError):validated_core(root)
                (root/'source.cc').write_bytes(b'one\r\ntwo\r\n');(archive/'source.cc').write_bytes(b'forged')
                with self.assertRaises(RuntimeError):validated_core(root)
if __name__=='__main__':unittest.main()
