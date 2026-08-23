"""拳头法则纯规则（防 LLM 幻觉——LLM 不参与结构判定，与 rules.py 同哲学）。

三餐模板来自用户画像：
- 早餐：粗粮 1 拳 + 蛋奶 1 份（鸡蛋或牛奶二选一）+ 蔬果 1 份，出门前 10 分钟
- 午餐：蔬菜 2 拳 + 主食 1 拳 + 肉类 1 拳，八分饱（工作日带饭，前一晚 Cook5 制）
- 晚餐：蔬菜 2 拳 + 鱼虾贝 1 拳，六分饱，无主食
"""

import random
from typing import Any, Dict, List, Optional, Tuple

# 每餐由若干 slot（餐位）构成；fists 为拳头数，kind 为食物大类
MEAL_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    "breakfast": [
        {"slot": "粗粮", "kind": "staple", "fists": 1, "candidates_hint": "玉米/紫薯/燕麦/全麦"},
        {"slot": "蛋奶", "kind": "protein", "fists": 1, "candidates_hint": "鸡蛋 或 牛奶 二选一"},
        {"slot": "蔬果", "kind": "veg", "fists": 1, "candidates_hint": "黄瓜一根/番茄一个"},
    ],
    "lunch": [
        {"slot": "蔬菜", "kind": "veg", "fists": 2,
         "candidates_hint": "带饭选耐复热：彩椒/西兰花/菌菇/根茎，忌绿叶菜复热变黄"},
        {"slot": "主食", "kind": "staple", "fists": 1, "candidates_hint": "杂粮饭/薯类"},
        {"slot": "肉类", "kind": "protein", "fists": 1,
         "candidates_hint": "鸡胸/牛肉/瘦猪肉；带饭忌整鱼（复热腥）"},
    ],
    "dinner": [
        {"slot": "蔬菜", "kind": "veg", "fists": 2, "candidates_hint": "任意熟菜"},
        {"slot": "鱼虾贝", "kind": "seafood", "fists": 1, "candidates_hint": "鱼/虾/贝"},
    ],
}

SATIETY: Dict[str, str] = {"lunch": "八分饱", "dinner": "六分饱"}

# 盒马货架分区（固定顺序，买菜清单分组用）
HIMA_CATEGORIES: List[str] = ["蔬菜", "水产", "肉蛋奶", "主食粮油", "调味"]

# 带饭友好标签：硬标准见 knowledge/recipes（Cook5 ≤25′ + 耐复热 + 末步装盒冷藏）
BENTO_TAG = "带饭友好"


def is_weekend(weekday: int) -> bool:
    """weekday 采 date.weekday()：周一=0 … 周日=6。"""
    return weekday >= 5


def validate_meal(meal_type: str, slots: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """校验菜谱拳头结构是否精确匹配三餐模板（slot 名 + kind + fists 逐位全等）。"""
    template = MEAL_TEMPLATES.get(meal_type)
    if template is None:
        return False, [f"未知餐次：{meal_type}"]
    problems: List[str] = []
    if len(slots) != len(template):
        problems.append(f"{meal_type} 应有 {len(template)} 个餐位，实际 {len(slots)} 个")
    for i, (t, s) in enumerate(zip(template, slots), start=1):
        fists = int(s.get("fists") or 0)
        if s.get("slot") != t["slot"] or s.get("kind") != t["kind"] or fists != t["fists"]:
            problems.append(
                f"第{i}餐位应为 {t['slot']}({t['kind']}){t['fists']}拳，"
                f"实际 {s.get('slot')}({s.get('kind')}){fists}拳"
            )
    return not problems, problems


def pick_recipe(
    candidates: List[Dict[str, Any]],
    recent_3d: List[int],
    recent_1d: List[int],
    meal_type: str,
    weekday: int,
) -> Optional[int]:
    """轮换选菜：工作日午餐只选「带饭友好」；优先近 3 天未用，全用过放宽到近 1 天。

    返回 recipe_id；无可用候选（菜谱库为空/全被过滤）返回 None，由调用方兜底。
    """
    pool = list(candidates)
    if meal_type == "lunch" and not is_weekend(weekday):
        pool = [r for r in pool if BENTO_TAG in (r.get("tags") or [])]
    if not pool:
        return None
    for used in (set(recent_3d), set(recent_1d)):
        fresh = [r for r in pool if r["id"] not in used]
        if fresh:
            return random.choice(fresh)["id"]
    return None
