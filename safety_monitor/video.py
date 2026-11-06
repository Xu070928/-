"""Per-camera acquisition and bounded JPEG pre-roll; no inference claims."""
import json
import queue
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

class VideoWorker(threading.Thread):
    def __init__(self, camera, store, pre=10, post=20):
        super().__init__(daemon=True)
        self.camera, self.store = camera, store
        self.pre, self.post = pre, post
        self.stop_event = threading.Event()
        self.commands = queue.Queue(maxsize=16)
        self.lock = threading.Lock()
        self.latest = None
        self.status = "正在连接"
        self.fps = 0.0
        self.frames = deque()
        self.buffer_bytes = 0
        self.pending = []
        self.overlay = None

    def snapshot(self):
        with self.lock:
            return None if self.latest is None else self.latest.copy()

    def record(self, eid, person, state, roi):
        self.commands.put_nowait((eid, person, state, roi))

    def stop(self):
        self.stop_event.set()

    def _finish(self, item, complete):
        item["writer"].release()
        final = item["path"].with_suffix(".avi")
        item["path"].replace(final)
        metadata = {k: v for k, v in item.items() if k not in ("writer", "path")}
        metadata["complete"] = complete
        final.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        status = "已保存" if complete else "片段不完整（停止/断流）"
        if item["pre_actual"] < self.pre - 0.2:
            status += "；前置缓冲不足"
        self.store.media(item["id"], item["shot"], str(final), status)

    def _write(self, item, timestamp, frame):
        # CFR output at 30 fps, resampling wall-clock timestamps; duplicates are
        # explicitly reflected in metadata and never reported as inference FPS.
        target = int(max(0, timestamp - item["start"]) * 30)
        while item["written"] <= target:
            item["writer"].write(frame)
            item["written"] += 1

    def run(self):
        cap = None
        try:
            source = self.camera["source"]
            is_file = Path(source).is_file()
            if source.isdigit():
                cap = cv2.VideoCapture(int(source))
            else:
                cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG, [
                    cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
                    cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000])
            if not cap.isOpened():
                raise RuntimeError("视频源无法打开，请检查地址或文件")
            source_fps = cap.get(cv2.CAP_PROP_FPS)
            period = 1 / source_fps if is_file and 1 <= source_fps <= 240 else 0
            next_frame = time.monotonic()
            started, count = time.monotonic(), 0
            self.status = "视频预览；未启用自动违规识别"
            while not self.stop_event.is_set():
                if period:
                    self.stop_event.wait(max(0, next_frame - time.monotonic()))
                    next_frame += period
                ok, frame = cap.read()
                if not ok:
                    self.status = "视频结束" if is_file else "视频断流，请重新连接"
                    break
                stamp = time.monotonic()
                # Bounded 960px evidence resolution, documented in README.
                h, w = frame.shape[:2]
                frame = cv2.resize(frame, (960, max(2, int(h * 960 / w) // 2 * 2)))
                if self.overlay and stamp < self.overlay[0]:
                    _, person, state, roi = self.overlay
                    fh, fw = frame.shape[:2]
                    x1, y1, x2, y2 = [int(v * (fw if i % 2 == 0 else fh)) for i,v in enumerate(roi)]
                    color = (0,0,255) if state in ("未佩戴","佩戴不规范") else (0,180,255)
                    cv2.rectangle(frame, (x1,y1),(x2,y2), color, 3)
                    cv2.putText(frame, "MANUAL EVENT", (x1,max(20,y1-8)), 0, .6, color, 2)
                with self.lock:
                    self.latest = frame.copy()
                count += 1
                self.fps = count / max(.001, stamp - started)
                ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ok:
                    raise RuntimeError("截图编码失败")
                payload = jpg.tobytes()
                self.frames.append((stamp,payload))
                self.buffer_bytes += len(payload)
                while self.frames and (stamp-self.frames[0][0] > self.pre or self.buffer_bytes > 128*1024*1024):
                    self.buffer_bytes -= len(self.frames.popleft()[1])
                for item in list(self.pending):
                    self._write(item, min(stamp,item["end"]), frame)
                    if stamp >= item["end"]:
                        self._finish(item, True)
                        self.pending.remove(item)
                while not self.commands.empty():
                    eid, person, state, roi = self.commands.get_nowait()
                    self.overlay = (stamp + self.post, person, state, roi)
                    folder = self.store.root / "evidence" / datetime.now().strftime("%Y-%m-%d")
                    folder.mkdir(parents=True, exist_ok=True)
                    shot, path = folder / (eid+".jpg"), folder / (eid+".partial.avi")
                    evidence_frame = frame.copy()
                    fh, fw = frame.shape[:2]
                    coords = [int(v*(fw if i%2==0 else fh)) for i,v in enumerate(roi)]
                    cv2.rectangle(evidence_frame, tuple(coords[:2]), tuple(coords[2:]), (0,0,255) if state in ("未佩戴","佩戴不规范") else (0,180,255), 3)
                    cv2.imencode(".jpg", evidence_frame)[1].tofile(str(shot))
                    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30, (fw,fh))
                    if not writer.isOpened():
                        self.store.media(eid,str(shot),"","片段编码失败")
                        continue
                    first = self.frames[0][0]
                    item = dict(id=eid, writer=writer, path=path, shot=str(shot),
                                start=first, end=stamp+self.post, pre_actual=stamp-first,
                                written=0, camera=self.camera["name"], location=self.camera["location"],
                                person=person, state=state, origin="人工登记", roi=roi,
                                output_fps=30, inference_fps=None)
                    for t, data in self.frames:
                        decoded = cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
                        self._write(item,t,decoded)
                    self.pending.append(item)
                    self.store.media(eid,str(shot),"","录制中")
        except Exception as exc:
            # Do not persist camera URLs/passwords in logs.
            self.status = "视频处理失败：" + type(exc).__name__
        finally:
            if cap is not None:
                cap.release()
            for item in self.pending:
                try:
                    self._finish(item,False)
                except Exception:
                    self.store.media(item["id"],item["shot"],"","片段保存失败")
            while not self.commands.empty():
                eid, *_ = self.commands.get_nowait()
                self.store.media(eid,"","","无可用帧")
