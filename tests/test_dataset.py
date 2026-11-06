import tempfile
import unittest
import zipfile
from pathlib import Path
from tools.prepare_dataset import prepare

class DatasetTests(unittest.TestCase):
    def test_remap_copy_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/"source.zip"
            with zipfile.ZipFile(src,"w") as z:
                for split,stem,label in [
                    ("train","WH-climb 7_frame_000000","0 .5 .5 .1 .1"),
                    ("train","WH-work 1_frame_000000","0 .5 .5 .1 .1\n1 .5 .5 .2 .2"),
                    ("val","WH-climb 3_frame_000000","2 .5 .5 .1 .1"),
                    ("test","WH-climb 2_frame_000000","1 .5 .5 .1 .1")]:
                    z.writestr(f"safety belt/data/{split}/images/{stem}.jpg",b"fixture")
                    z.writestr(f"safety belt/data/{split}/labels/{stem}.txt",label)
            original=src.read_bytes()
            target=Path(tmp)/"corrected"
            report=prepare(src,target)
            self.assertEqual(report["remapped"],3)
            self.assertEqual(src.read_bytes(),original)
            label=(target/"train/labels/WH-work 1_frame_000000.txt").read_text()
            self.assertEqual([r.split()[0] for r in label.splitlines()],["1","2"])
            with self.assertRaises(ValueError):prepare(src,target)
