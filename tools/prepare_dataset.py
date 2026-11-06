"""Create a corrected dataset copy from original ZIP, never edit source."""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

def prepare(archive, output):
    archive,output=Path(archive),Path(output)
    if output.exists(): raise ValueError("输出目录已存在，请使用新版本目录")
    with zipfile.ZipFile(archive) as z:
        selected=[]
        for info in z.infolist():
            m=re.fullmatch(r"safety belt/data/(train|val|test)/(images|labels)/([^/]+[.](jpg|txt))",info.filename)
            if m:
                name=m[3]
                if "\\" in name or ":" in name or ".." in name: raise ValueError("不安全路径")
                selected.append((info,m[1],m[2],name))
        if not selected: raise ValueError("未找到预期数据目录")
        output.mkdir(parents=True)
        changed=0;objects=0
        for info,split,kind,name in selected:
            data=z.read(info)
            if kind=="labels":
                lines=[]
                for line in data.decode("utf-8-sig").splitlines():
                    if not line.strip(): continue
                    parts=line.split()
                    if len(parts)!=5: raise ValueError("无效YOLO标签："+name)
                    cid=int(parts[0]);coords=list(map(float,parts[1:]))
                    if cid not in (0,1,2) or not all(0<=v<=1 for v in coords) or min(coords[2:])<=0:
                        raise ValueError("标签越界："+name)
                    new=cid
                    if name.startswith("WH-climb 7"):
                        if cid!=0: raise ValueError("climb 7 原始映射与预期不同")
                        new=1
                    elif name.startswith("WH-work 1"):
                        if cid not in (0,1): raise ValueError("work 1 原始映射与预期不同")
                        new=cid+1
                    changed+=new!=cid;objects+=1
                    lines.append(" ".join([str(new)]+parts[1:]))
                data=("\n".join(lines)+"\n").encode()
            dest=output/split/kind/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(data)
    sources={}
    for split in ("train","val","test"):
        images={p.stem for p in (output/split/"images").glob("*.jpg")}
        labels={p.stem for p in (output/split/"labels").glob("*.txt")}
        if images!=labels: raise ValueError("图像标签不配对："+split)
        sources[split]={re.sub(r"(?:_frame)?_\d+$","",n) for n in images}
    for a,b in (("train","val"),("train","test"),("val","test")):
        if sources[a]&sources[b]: raise ValueError("视频源跨集合泄漏")
    (output/"data.yaml").write_text(
        "path: "+json.dumps(str(output.resolve()).replace("\\","/"))+
        "\ntrain: train/images\nval: val/images\ntest: test/images\nnames: ['safety hook', 'safety rope', 'safety belt']\n",
        encoding="utf-8")
    with archive.open("rb") as stream: sha=hashlib.file_digest(stream,"sha256").hexdigest()
    report=dict(source_sha256=sha,objects=objects,remapped=changed,
                sources={k:sorted(v) for k,v in sources.items()},
                note="仅修复已确认类别ID；不保证框质量；不含违规/锚点标签")
    (output/"manifest.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("archive");p.add_argument("output")
    a=p.parse_args()
    print(json.dumps(prepare(a.archive,a.output),ensure_ascii=False,indent=2))
