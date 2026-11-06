import tempfile
import unittest
from pathlib import Path
from openpyxl import load_workbook
from safety_monitor.rules import Evidence, decide
from safety_monitor.storage import Store
from tools.evaluate import evaluate

class RulesTests(unittest.TestCase):
    def test_unknown_is_review(self):
        self.assertEqual(decide(Evidence()).state,"人工复核")
        self.assertEqual(decide(Evidence(True,True,True,None)).state,"人工复核")
    def test_non_workwear_ignored(self):
        self.assertEqual(decide(Evidence(False,True,False)).state,"忽略")
    def test_ground_review(self):
        self.assertEqual(decide(Evidence(True,False,False)).state,"人工复核")
    def test_violations_immediate(self):
        self.assertEqual(decide(Evidence(True,True,False)).state,"未佩戴")
        self.assertEqual(decide(Evidence(True,True,True,False)).state,"佩戴不规范")
        self.assertEqual(decide(Evidence(True,True,True,True,None,True)).state,"佩戴不规范")
    def test_anchor_unknown_not_normal(self):
        self.assertEqual(decide(Evidence(True,True,True,True,None,False)).state,"人工复核")
        self.assertEqual(decide(Evidence(True,True,True,True,True,False)).state,"规范佩戴")
    def test_occlusion_never_assumed_unhooked(self):
        self.assertEqual([decide(Evidence(True,True,True,h,True,False)).state for h in (True,None,True)],
                         ["规范佩戴","人工复核","规范佩戴"])

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.s=Store(self.tmp.name)
        self.s.add_user("admin","long-password","admin")
        self.admin=self.s.login("admin","long-password")
        self.s.add_user("operator","long-password","operator",self.admin)
        self.op=self.s.login("operator","long-password")
    def tearDown(self): self.tmp.cleanup()
    def test_auth_and_roles(self):
        with self.assertRaises(PermissionError): self.s.login("admin","wrong")
        with self.assertRaises(PermissionError): self.s.add_camera(self.op,"a","b","0")
        with self.assertRaises(PermissionError): self.s.export(self.op,Path(self.tmp.name)/"x.xlsx")
        with self.assertRaises(PermissionError): self.s.add_user("evil","long-password","admin")
        self.s.logout(self.op)
        with self.assertRaises(PermissionError): self.s.cameras(self.op)
    def test_history_reviews_export_and_persistence(self):
        cam=dict(name="=1+1",location="塔1",source="0")
        eid=self.s.add_event(self.op,cam,"p1",decide(Evidence(True,True,False)))
        self.s.review(self.op,eid,"确认违规","=HYPERLINK(\"x\")")
        self.s.review(self.admin,eid,"仍无法判断","第二次复核")
        rows=self.s.events(self.admin,verdict="仍无法判断",text="p1")
        self.assertEqual(len(rows),1)
        path=Path(self.tmp.name)/"report.xlsx"
        self.s.export(self.admin,path)
        wb=load_workbook(path)
        self.assertEqual(wb["事件台账"]["C2"].data_type,"s")
        self.assertEqual(wb["复核轨迹"].max_row,3)
        self.assertEqual(wb["复核轨迹"]["E2"].data_type,"s")
        wb.close()
        s2=Store(self.tmp.name)
        token=s2.login("admin","long-password")
        self.assertEqual(s2.events(token)[0]["id"],eid)

class EvaluationTests(unittest.TestCase):
    def test_abstention_counts_as_miss(self):
        r=dict(video="v",frame="1",person="1",truth="未佩戴",prediction="人工复核")
        result=evaluate([r])
        self.assertFalse(result["passed"])
        self.assertEqual(result["metrics"]["未佩戴"]["fn"],1)
    def test_absent_class_not_pass(self):
        r=dict(video="v",frame="1",person="1",truth="未佩戴",prediction="未佩戴")
        self.assertFalse(evaluate([r])["passed"])
    def test_duplicate_rejected(self):
        r=dict(video="v",frame="1",person="1",truth="未佩戴",prediction="未佩戴")
        with self.assertRaises(ValueError): evaluate([r,r])

if __name__=="__main__": unittest.main()
