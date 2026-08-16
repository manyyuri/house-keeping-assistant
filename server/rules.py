"""断舍离硬规则（代码化防幻觉，LLM 不可覆盖）。

各规则标注理论出处：项目内置知识库 knowledge/duansheli/。
"""

from collections import Counter
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

# 犹豫物品观察期（天）——"心的保质期"复查（ch2）
QUARANTINE_DAYS = 90


def danshari_score(items: List[Dict[str, Any]], messiness: str = "low") -> int:
    """0=急需断舍离, 100=状态极佳。纯规则计算，LLM 不可覆盖。

    - 每件该丢 -8：「舍是施与」，该丢的每件都是阻塞代谢的废品（ch2 三层筛子·第一层）
    - 每件犹豫 -5：犹豫即执念残留（ch1 三类囤积倾向：时间轴不在"现在"）
    - 混乱度扣分：「相」论（ch4）：环境之相映射内心之相
    - 同类囤积超量扣分：80/20 忘却物定律（ch2），每超 1 件 -4
    """
    score = 100
    for it in items:
        qty = int(it.get("quantity") or 1)
        if it.get("keep_status") == "discard":
            score -= 8 * qty
        elif it.get("keep_status") == "hesitate":
            score -= 5 * qty

    if messiness == "high":
        score -= 15
    elif messiness == "medium":
        score -= 8

    counter: Counter = Counter()
    for it in items:
        counter[it.get("category") or "other"] += int(it.get("quantity") or 1)
    for _cat, n in counter.items():
        if n > 2:
            score -= 4 * (n - 2)

    return max(0, min(100, score))


def quarantine_until_today() -> str:
    return (date.today() + timedelta(days=QUARANTINE_DAYS)).isoformat()


def expired_quarantine_ids() -> List[int]:
    """观察期已到且仍为 hesitate 的物品 id（"心的保质期"检验，ch2）。

    由 db 查询，供 GET /api/stats 返回，前端弹提醒：观察期已到，请重新判定。
    """
    # 延迟导入避免循环依赖
    from server import db

    return [it["id"] for it in db.expired_quarantine_items()]


def score_grade(score: int) -> str:
    """评分分级文案（供前端配色/后端 summary 参考）。"""
    if score <= 40:
        return "急需断舍离"
    if score <= 70:
        return "有待整顿"
    return "状态良好"


def normalize_messiness(value: Optional[str]) -> str:
    if value in ("low", "medium", "high"):
        return value
    return "low"
