"""Evidence-only rule engine. None means unknown, never negative evidence."""
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class Evidence:
    workwear: Optional[bool] = None
    at_height: Optional[bool] = None
    wearing: Optional[bool] = None
    hooked: Optional[bool] = None
    anchor_reliable: Optional[bool] = None
    below_workplane: Optional[bool] = None

@dataclass(frozen=True)
class Decision:
    state: str
    reason: str

def decide(e: Evidence) -> Decision:
    if e.workwear is False:
        return Decision("忽略", "非高空工作服人员")
    if e.workwear is None or e.at_height is not True:
        return Decision("人工复核", "工作服或高处作业状态未确认")
    if e.wearing is False:
        return Decision("未佩戴", "已确认未佩戴安全带")
    if e.wearing is None:
        return Decision("人工复核", "佩戴状态不可辨认")
    if e.hooked is False:
        return Decision("佩戴不规范", "已确认挂钩未挂")
    if e.below_workplane is True:
        return Decision("佩戴不规范", "挂点低于工作面")
    if e.anchor_reliable is False:
        return Decision("佩戴不规范", "已确认锚点不可靠（需有现场标准）")
    if e.hooked is None or e.anchor_reliable is None or e.below_workplane is None:
        return Decision("人工复核", "连接、锚点或挂点高度证据不足")
    return Decision("规范佩戴", "各项证据均确认合规")

VIOLATIONS = {"未佩戴", "佩戴不规范"}
