import tempfile
import time
import unittest
from pathlib import Path
import cv2
import numpy as np
from safety_monitor.video import VideoWorker
from safety_monitor.storage import Store
from safety_monitor.rules import Decision

class VideoTests(unittest.TestCase):
    def test_clip_and_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=root/"fixture.avi"
            writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*"MJPG"),30,(320,240))
            self.assertTrue(writer.isOpened())
            for i in range(120): writer.write(np.full((240,320,3),i%255,np.uint8))
            writer.release()
            s=Store(root/"runtime")
            s.add_user("admin","password-123","admin")
            token=s.login("admin","password-123")
            cam=dict(name="测试",location="测试位",source=str(path))
            worker=VideoWorker(cam,s,pre=.4,post=.4)
            worker.start()
            try:
                deadline=time.monotonic()+10
                while worker.snapshot() is None and worker.is_alive() and time.monotonic()<deadline:
                    time.sleep(.05)
                self.assertIsNotNone(worker.snapshot(),worker.status)
                eid=s.add_event(token,cam,"p1",Decision("未佩戴","测试"))
                worker.record(eid,"p1","未佩戴",[.1,.1,.5,.9])
                while time.monotonic()<deadline:
                    row=s.events(token)[0]
                    if row["clip"]: break
                    time.sleep(.05)
                self.assertTrue(row["clip"],row)
                self.assertTrue(Path(row["screenshot"]).is_file())
                cap=cv2.VideoCapture(row["clip"])
                self.assertTrue(cap.read()[0])
                cap.release()
            finally:
                worker.stop()
                worker.join(10)
            self.assertFalse(worker.is_alive())

if __name__=="__main__": unittest.main()
