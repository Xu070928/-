"""Aligned person-frame evaluation. Abstentions count as missed violations."""
import argparse
import csv
import json
CLASSES = ("未佩戴", "佩戴不规范")

def evaluate(rows):
    if not rows: raise ValueError("评估集不能为空")
    seen=set()
    allowed=set(CLASSES)|{"规范佩戴","人工复核","忽略"}
    for r in rows:
        key=(r["video"],r["frame"],r["person"])
        if key in seen: raise ValueError("重复 person-frame 样本")
        seen.add(key)
        if r["truth"] not in allowed or r["prediction"] not in allowed:
            raise ValueError("未知类别")
    metrics={}
    for cls in CLASSES:
        tp=sum(r["truth"]==cls and r["prediction"]==cls for r in rows)
        fp=sum(r["truth"]!=cls and r["prediction"]==cls for r in rows)
        fn=sum(r["truth"]==cls and r["prediction"]!=cls for r in rows)
        precision=tp/(tp+fp) if tp+fp else None
        recall=tp/(tp+fn) if tp+fn else None
        metrics[cls]=dict(tp=tp,fp=fp,fn=fn,precision=precision,recall=recall,
                         passed=precision is not None and recall is not None and precision>=.95 and recall>=.95)
    return dict(samples=len(rows),videos=len({r["video"] for r in rows}),
                review_rate=sum(r["prediction"]=="人工复核" for r in rows)/len(rows),
                metrics=metrics,passed=all(m["passed"] for m in metrics.values()),
                scope="已对齐人员逐帧评估；不代表事件级或端到端验收")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("csv",help="UTF-8 CSV: video,frame,person,truth,prediction")
    p.add_argument("--output",default="evaluation.json")
    a=p.parse_args()
    with open(a.csv,encoding="utf-8-sig",newline="") as stream:
        result=evaluate(list(csv.DictReader(stream)))
    with open(a.output,"w",encoding="utf-8") as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2))
