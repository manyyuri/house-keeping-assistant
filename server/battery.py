"""三格电引擎：按当天精力供给「最小行动 + 餐食」（省力概念核心，CONCEPT §6.1）。

电量不是 UI 装饰，必须真的改变内容供给（CONCEPT §11 风险#3）：
- 满格 → 一个 ≤15 分钟任务 + 可选菜单
- 半格 → 一个 ≤5 分钟任务 + 直接告诉今天吃什么
- 没电 → 一个 ≤2 分钟任务（或「今天就歇着」）+ 一句不指责的话

诚实原则（CONCEPT §11 风险#2）：只有真实完成的动作（任务 done / 用餐 eaten）才计入
努力轨迹；兜底建议（FALLBACK_TASKS）不伪造加分，只给指引。
"""

import datetime as dt
from typing import Any, Dict, List, Optional

from server import db, meals

# 三格电档位：max_min 决定「这格电只配多大的任务」
ENERGY_LEVELS: Dict[str, Dict[str, Any]] = {
    "full": {"max_min": 15, "label": "满格", "title": "今天力气还够", "mode": "choose"},
    "half": {"max_min": 5, "label": "半格", "title": "还剩一点力气", "mode": "give"},
    "empty": {"max_min": 2, "label": "没电", "title": "今天有点累了", "mode": "rest"},
}

# 兜底「最小行动建议」库：原子化、失败零代价、不制造愧疚。
# 无待办任务时按日轮换给出一条（确定性，不重复烦人）。
FALLBACK_TASKS: List[Dict[str, Any]] = [
    {"type": "discard", "title": "扔掉一件明显该扔的旧物", "est_minutes": 2,
     "steps": ["拿个袋子", "找一件明显该扔的", "丢进去"]},
    {"type": "organize", "title": "把桌上 3 件杂物放回原位", "est_minutes": 3,
     "steps": ["只看桌面", "挑 3 件", "各归其位"]},
    {"type": "store", "title": "把门口散落的鞋摆回鞋柜", "est_minutes": 3,
     "steps": ["弯腰", "捡起", "摆进去"]},
    {"type": "clean", "title": "擦干净洗手台台面", "est_minutes": 5,
     "steps": ["拿块抹布", "抹一圈", "挂回去"]},
    {"type": "discard", "title": "清空冰箱里 1 瓶过期调料", "est_minutes": 5,
     "steps": ["开冰箱", "看保质期", "扔掉过期的"]},
    {"type": "organize", "title": "把玄关的三双鞋对齐", "est_minutes": 5,
     "steps": ["蹲下来", "摆正", "起身"]},
    {"type": "store", "title": "竖立折叠 3 件 T 恤放进抽屉", "est_minutes": 10,
     "steps": ["拿出 3 件 T 恤", "卷成筒", "竖放进抽屉"]},
    {"type": "clean", "title": "给书桌抽屉里 5 件杂物分类", "est_minutes": 10,
     "steps": ["打开抽屉", "分成两类", "放回原位"]},
    {"type": "discard", "title": "把不会再穿的 5 件衣服装进捐赠袋", "est_minutes": 15,
     "steps": ["拿个袋子", "挑 5 件不穿的", "装袋放玄关"]},
    {"type": "clean", "title": "擦拭衣柜层板并吸尘柜底", "est_minutes": 15,
     "steps": ["清空一层", "擦干净", "吸尘"]},
]

ENCOURAGEMENT: Dict[str, str] = {
    "full": "满电的一天，值得做一件 15 分钟的事。",
    "half": "还剩半格，够完成一件 5 分钟的小事。",
    "empty": "今天你已经做得很好了。能歇就歇，不勉强。",
}

MEAL_LABEL = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}


def recommend_task(level: str) -> Dict[str, Any]:
    """按档位给一个最小行动：先挑真实待办任务（est_minutes ≤ 档位上限，取最短），
    没有则给兜底建议。返回统一结构，source 区分 task / suggestion（诚实记账）。"""
    max_min = ENERGY_LEVELS[level]["max_min"]
    pending = [
        t for t in db.list_tasks()
        if t.get("status") in ("todo", "doing")
        and t.get("est_minutes") is not None
        and int(t["est_minutes"]) <= max_min
    ]
    if pending:
        t = min(pending, key=lambda x: (int(x["est_minutes"]), -int(x["id"])))
        return {
            "source": "task",
            "id": t["id"],
            "plan_id": t["plan_id"],
            "room": t.get("plan_room"),
            "type": t["type"],
            "title": t["title"],
            "est_minutes": int(t["est_minutes"]),
            "steps": t.get("steps") or [],
        }
    pool = [f for f in FALLBACK_TASKS if f["est_minutes"] <= max_min]
    f = pool[dt.date.today().toordinal() % len(pool)]
    return {**f, "source": "suggestion", "id": None, "plan_id": None, "room": None}


def meal_supply(level: str) -> Dict[str, Any]:
    """按档位给餐食：满格=可选菜单，半格=直接给今天晚餐，没电=别勉强。
    生成失败（如菜谱缺失）降级为温和提示，绝不崩首页。"""
    mode = ENERGY_LEVELS[level]["mode"]
    try:
        day = meals.ensure_day()
        lunch = day["meals"].get("lunch") or {}
        dinner = day["meals"].get("dinner") or {}
    except Exception:  # noqa: BLE001 — 三餐是加分项，不是首页的主干
        day = None

    def _m(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        r = (p.get("recipe") or {})
        name = r.get("name")
        if not name:
            return None
        return {"type": p.get("meal_type"), "name": name, "cook_minutes": r.get("cook_minutes")}

    if mode == "rest":
        return {"give": False, "meal": None, "meals": [],
                "text": "今天吃什么都行，别勉强。能吃上一口热的，就是赢。"}
    if day is None:
        return {"give": False, "meal": None, "meals": [],
                "text": "三餐还没准备好，去三餐页看一眼就知道吃什么了。"}
    if mode == "give":
        d = _m(dinner)
        return {"give": True, "meal": d, "meals": [],
                "text": "今晚就吃这个，不用选。" if d else "今晚吃什么，到了三餐页就知道了。"}
    # mode == "choose"：满格 → 可选菜单（午餐 + 晚餐）
    meals_ = [m for m in (_m(lunch), _m(dinner)) if m]
    return {"give": False, "meal": None, "meals": meals_,
            "text": "菜单已备好，随便挑，去三餐页不费脑。"}


def trajectory() -> Dict[str, Any]:
    """努力轨迹（加分制表达）：本周完成的最小动作数 vs 上周，只算真实完成。"""
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    last_monday = monday - dt.timedelta(days=7)
    next_monday = monday + dt.timedelta(days=7)

    def _week(start: dt.date, end: dt.date) -> int:
        s, e = start.isoformat(), end.isoformat()
        return (
            db.count_done_tasks_between(s, e)
            + db.count_eaten_meals_between(s, e)
        )

    this = _week(monday, next_monday)
    last = _week(last_monday, monday)
    delta = this - last
    if delta > 0:
        line = f"这周你完成了 {this} 件最小的事，比上周多 {delta} 件。"
    elif delta < 0:
        line = f"这周你完成了 {this} 件最小的事，比上周少 {-delta} 件。没关系，这周还没过完。"
    else:
        line = f"这周你完成了 {this} 件最小的事。"
    return {"this_week": this, "last_week": last, "delta": delta, "line": line}


def home_payload(level: str) -> Dict[str, Any]:
    """组装 /api/home 负载：档位 + 最小行动 + 餐食 + 一句不指责的话 + 努力轨迹。"""
    lv = ENERGY_LEVELS[level]
    return {
        "energy": level,
        "level": {"key": level, "max_min": lv["max_min"], "label": lv["label"],
                  "title": lv["title"]},
        "task": recommend_task(level),
        "rest_allowed": level == "empty",
        "meal": meal_supply(level),
        "encouragement": ENCOURAGEMENT[level],
        "trajectory": trajectory(),
    }
