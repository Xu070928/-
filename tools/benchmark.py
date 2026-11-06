"""Optional YOLO component benchmark. Not a violation detection benchmark."""
import argparse
import hashlib
import json
import platform
import time
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--model",required=True)
    p.add_argument("--video",required=True)
    p.add_argument("--device",default="cpu")
    p.add_argument("--frames",type=int,default=300)
    p.add_argument("--output",default="benchmark.json")
    a=p.parse_args()
    if a.frames<1: raise ValueError("frames must be positive")
    model_path,video_path=Path(a.model),Path(a.video)
    if not model_path.is_file() or not video_path.is_file():
        raise ValueError("必须提供本地权重与本地视频，禁止隐式下载")
    import cv2
    import torch
    import ultralytics
    from ultralytics import YOLO
    model=YOLO(str(model_path))
    cap=cv2.VideoCapture(str(video_path))
    ok,frame=cap.read()
    if not ok: raise ValueError("视频无法解码")
    for _ in range(5):
        model.predict(frame,imgsz=640,device=a.device,verbose=False)
    cap.set(cv2.CAP_PROP_POS_FRAMES,0)
    count=0;latencies=[]
    start=time.perf_counter()
    while count<a.frames:
        tick=time.perf_counter()
        ok,frame=cap.read()
        if not ok: break
        model.predict(frame,imgsz=640,device=a.device,verbose=False)
        if torch.cuda.is_available() and a.device!="cpu": torch.cuda.synchronize()
        latencies.append(time.perf_counter()-tick)
        count+=1
    elapsed=time.perf_counter()-start
    cap.release()
    if not count: raise ValueError("无有效评估帧")
    with model_path.open("rb") as stream: digest=hashlib.file_digest(stream,"sha256").hexdigest()
    result=dict(frames=count,fps=count/elapsed,
                p95_latency_ms=sorted(latencies)[min(count-1,int(count*.95))]*1000,
                model_sha256=digest,device=a.device,platform=platform.platform(),
                torch=torch.__version__,ultralytics=ultralytics.__version__,
                cuda_available=torch.cuda.is_available(),
                scope="解码+YOLO部件检测；不含跟踪、违规判断、界面与录像；不作为完整30FPS验收")
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
