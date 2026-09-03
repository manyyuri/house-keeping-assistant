"""三餐推荐引擎（业务服务层）。

同步为主（SQLite DAO 同步，FastAPI 线程池安全）；LLM 仅用于晚餐小贴士且可降级。
生成规则全部走 meal_rules 纯函数——断电/Ollama 不可用时推荐、换菜、清单完整可用。
"""

import asyncio
import json
import logging
import random
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from server import db, meal_rules, preferences

logger = logging.getLogger("danshari.meals")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = PROJECT_ROOT / "knowledge" / "recipes" / "recipes.json"

MEAL_ORDER = ("breakfast", "lunch", "dinner")
WEEKDAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
MEAL_SHORT = {"breakfast": "早", "lunch": "午", "dinner": "晚"}

# 便当制作锁定时刻：制作日（前一天）19:00 起不可换菜
BENTO_LOCK_HOUR = 19


class BentoLocked(Exception):
    """便当已做好/正在做，换菜被拒绝。"""


# ---------- 种子导入 ----------

def seed_default_recipes() -> int:
    """首次启动导入种子菜谱库（表非空则跳过）。防御性过滤结构不合法项。"""
    if db.list_recipes():
        return 0
    rows = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    valid = [r for r in rows if meal_rules.validate_meal(r["meal_type"], r["slots"])[0]]
    skipped = len(rows) - len(valid)
    if skipped:
        logger.warning("种子菜谱 %d 道结构不合法，已跳过", skipped)
    return db.seed_recipes(valid)


def sync_default_recipes() -> int:
    """老库升级：把最新 seed 同步进非空 recipes 表（补 cuisine、改名菜、新菜）。

    返回新增条数；已是最新时返回 0。幂等。
    """
    rows = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    added = db.sync_seed_recipes(rows)
    if added:
        logger.info("菜谱库同步：新增 %d 道（knowledge/recipes）", added)
    return added


# ---------- 生成 ----------

def _parse_date(s: Optional[str]) -> date:
    if not s:
        return date.today()
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise ValueError("日期格式应为 yyyy-mm-dd")


def _eligible(pool: List[Dict[str, Any]], d: date, meal_type: str) -> List[Dict[str, Any]]:
    """工作日午餐只留带饭友好（与 pick_recipe 同口径）。"""
    if meal_type == "lunch" and not meal_rules.is_weekend(d.weekday()):
        return [r for r in pool if meal_rules.BENTO_TAG in (r.get("tags") or [])]
    return pool


def _try_pick(pool: List[Dict[str, Any]], d: date, meal_type: str) -> Optional[Dict[str, Any]]:
    """轮换选一道：先近 3 天未用，全用过放宽近 1 天，仍无则池内随机（带饭口径）。"""
    date_str = d.isoformat()
    rid = meal_rules.pick_recipe(
        pool,
        recent_3d=db.recent_recipe_ids(meal_type, date_str, days=3),
        recent_1d=db.recent_recipe_ids(meal_type, date_str, days=1),
        meal_type=meal_type,
        weekday=d.weekday(),
    )
    if rid is not None:
        return db.get_recipe(rid)
    elig = _eligible(pool, d, meal_type)
    return random.choice(elig) if elig else None


def _pick_for(d: date, meal_type: str) -> Optional[Dict[str, Any]]:
    """按轮换规则选一道菜谱；库太小导致轮换失败时兜底随机。

    口味偏好：先剔忌口食材 → 优先在偏好菜系里轮换；偏好菜系轮换耗尽再回退可吃全量。
    """
    candidates = db.list_recipes(meal_type)
    prefs = preferences.load()
    eat, fav = preferences.split_pool(candidates, prefs)
    if not eat:  # 忌口把整库挡光 → 兜底全库（宁可换菜也别饿着）
        eat = candidates
    fav = [r for r in fav if r in eat]

    rec = _try_pick(fav or eat, d, meal_type)
    if rec is not None:
        return rec
    if fav:  # 偏好菜系被轮换耗尽了，才回退到可吃全量
        rec = _try_pick(eat, d, meal_type)
    return rec


def _lunch_mode(d: date) -> str:
    return "cook" if meal_rules.is_weekend(d.weekday()) else "bento"


def _ensure_one_meal(d: date, meal_type: str) -> Dict[str, Any]:
    """幂等生成某日某餐；食材只在「次日及以后」进买菜清单。"""
    existing = db.get_meal_plan(d.isoformat(), meal_type)
    if existing:
        return existing
    recipe = _pick_for(d, meal_type)
    if recipe is None:
        raise ValueError(f"菜谱库缺少 {meal_type} 候选，请补充 knowledge/recipes")
    mode = _lunch_mode(d) if meal_type == "lunch" else "cook"
    plan = db.upsert_meal_plan(d.isoformat(), meal_type, recipe["id"], mode)
    if d.isoformat() > date.today().isoformat():
        db.add_grocery_rows(
            [
                {"plan_date": d.isoformat(), "meal_type": meal_type,
                 "name": ing["name"], "amount": ing.get("amount"), "hima": ing.get("hima")}
                for ing in recipe["ingredients"]
            ]
        )
    return plan


def ensure_day(date_str: Optional[str] = None) -> Dict[str, Any]:
    """幂等生成某日三餐（连带次日三餐占位，供晚上下单盒马），返回当日负载。"""
    d = _parse_date(date_str)
    for target in (d, d + timedelta(days=1)):
        for mt in MEAL_ORDER:
            _ensure_one_meal(target, mt)
    return _day_payload(d)


# ---------- 负载组装 ----------

def _meal_out(plan: Optional[Dict[str, Any]], d: date) -> Optional[Dict[str, Any]]:
    """meal_plans 行 + recipe 详情；晚餐附 bento_preview（明日便当摘要）。"""
    if not plan:
        return None
    out = dict(plan)
    out["recipe"] = db.get_recipe(plan["recipe_id"]) if plan["recipe_id"] else None
    if plan["meal_type"] == "dinner":
        out["bento_preview"] = None
        tomorrow_lunch = db.get_meal_plan((d + timedelta(days=1)).isoformat(), "lunch")
        if tomorrow_lunch and tomorrow_lunch["mode"] == "bento" and tomorrow_lunch["recipe_id"]:
            r = db.get_recipe(tomorrow_lunch["recipe_id"])
            if r:
                out["bento_preview"] = {"name": r["name"], "cook_minutes": r["cook_minutes"]}
    return out


def _day_payload(d: date) -> Dict[str, Any]:
    plans = db.get_day_meals(d.isoformat())
    payload: Dict[str, Any] = {
        "date": d.isoformat(),
        "weekday": WEEKDAY_LABELS[d.weekday()],
        "meals": {mt: _meal_out(plans.get(mt), d) for mt in MEAL_ORDER},
    }
    nxt = d + timedelta(days=1)
    tm = db.get_day_meals(nxt.isoformat())
    payload["tomorrow_preview"] = {
        "date": nxt.isoformat(),
        **{
            mt: (db.get_recipe(tm[mt]["recipe_id"]) or {}).get("name")
            if mt in tm and tm[mt]["recipe_id"] else None
            for mt in MEAL_ORDER
        },
    }
    return payload


# ---------- 换菜 ----------

def _bento_locked(d: date) -> bool:
    """便当制作日（前一天）19:00 起锁定：菜已在做/已装盒。"""
    cook_day = d - timedelta(days=1)
    now = datetime.now()
    return now.date() > cook_day or (now.date() == cook_day and now.hour >= BENTO_LOCK_HOUR)


def reroll(date_str: str, meal_type: str) -> Dict[str, Any]:
    """换一个：排除当前菜后重选，同步买菜清单（删旧插新）。"""
    d = _parse_date(date_str)
    plan = db.get_meal_plan(d.isoformat(), meal_type)
    if not plan:
        raise ValueError("该餐尚未生成")
    if plan["mode"] == "bento" and _bento_locked(d):
        raise BentoLocked()
    if not plan["recipe_id"]:
        raise ValueError("该餐未绑定菜谱，无法换")

    candidates = db.list_recipes(meal_type)
    if plan["mode"] == "bento":
        candidates = [r for r in candidates if meal_rules.BENTO_TAG in (r.get("tags") or [])]
    # 口味偏好：先剔忌口；在偏好菜系里换，换尽再回退可吃全量
    prefs = preferences.load()
    eat, fav = preferences.split_pool(candidates, prefs)
    if not eat:
        eat = candidates
    fav = [r for r in fav if r in eat]

    def pick_from(pool: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        exclude = set(db.recent_recipe_ids(meal_type, d.isoformat(), days=3)) | {plan["recipe_id"]}
        p = [r for r in pool if r["id"] not in exclude]
        if not p:  # 放宽：只排除昨天与当前
            exclude = set(db.recent_recipe_ids(meal_type, d.isoformat(), days=1)) | {plan["recipe_id"]}
            p = [r for r in pool if r["id"] not in exclude]
        return random.choice(p) if p else None

    recipe = pick_from(fav or eat)
    if recipe is None and fav:
        recipe = pick_from(eat)
    if recipe is None:
        raise ValueError("菜谱轮换完毕，没有其他可选菜")

    new_plan = db.replace_meal_recipe(d.isoformat(), meal_type, recipe["id"])
    db.delete_grocery_for_meal(d.isoformat(), meal_type)
    if d.isoformat() > date.today().isoformat():
        db.add_grocery_rows(
            [
                {"plan_date": d.isoformat(), "meal_type": meal_type,
                 "name": ing["name"], "amount": ing.get("amount"), "hima": ing.get("hima")}
                for ing in recipe["ingredients"]
            ]
        )
    logger.info("换菜 %s %s → %s", d.isoformat(), meal_type, recipe["name"])
    return _meal_out(new_plan, d)


# ---------- 周视图 ----------

def week(start_str: Optional[str] = None) -> List[Dict[str, Any]]:
    """本周一~周日 7 天；今天及以后幂等生成，过去只读已存在的计划。"""
    today = date.today()
    start = _parse_date(start_str) if start_str else today - timedelta(days=today.weekday())
    days = [start + timedelta(days=i) for i in range(7)]
    for d in days:
        if d >= today:
            ensure_day(d.isoformat())
    rows = db.list_meal_plans(days[0].isoformat(), days[-1].isoformat())
    by_date: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for r in rows:
        by_date.setdefault(r["plan_date"], {})[r["meal_type"]] = r
    out = []
    for d in days:
        day_plans = by_date.get(d.isoformat(), {})
        out.append({
            "date": d.isoformat(),
            "weekday": WEEKDAY_LABELS[d.weekday()],
            "is_today": d == today,
            "meals": {
                mt: (
                    {"name": p["recipe_name"], "mode": p["mode"], "status": p["status"]}
                    if (p := day_plans.get(mt)) and p.get("recipe_name") else None
                )
                for mt in MEAL_ORDER
            },
        })
    return out


# ---------- 买菜清单 ----------

def grocery(days: int = 3) -> Dict[str, Any]:
    """聚合 [明天, 今天+days] 的食材：同名合并、按盒马分区分组、附覆盖餐次。"""
    today = date.today()
    window = [today + timedelta(days=i) for i in range(1, days + 1)]
    for d in window:  # 幂等铺满窗口（ensure 会多铺一天，聚合时被窗口过滤）
        for mt in MEAL_ORDER:
            _ensure_one_meal(d, mt)
    rows = db.list_grocery(window[0].isoformat(), window[-1].isoformat())

    by_cat: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for r in rows:
        by_cat.setdefault(r.get("hima_category") or "调味", {}).setdefault(r["name"], []).append(r)
    groups = []
    for cat in meal_rules.HIMA_CATEGORIES:
        bucket = by_cat.pop(cat, {})
        if not bucket:
            continue
        items = []
        for name, rs in bucket.items():
            items.append({
                "name": name,
                "amounts": sorted({r["amount"] for r in rs if r["amount"]}),
                "meals": [f"{r['plan_date'][5:].replace('-', '/')} {MEAL_SHORT.get(r['meal_type'], '')}"
                          for r in rs],
                "ids": [r["id"] for r in rs],
                "checked": all(r["checked"] for r in rs),
            })
        groups.append({"category": cat, "items": items})
    total = sum(len(g["items"]) for g in groups)
    pending = sum(1 for g in groups for it in g["items"] if not it["checked"])
    return {
        "days": days,
        "through_date": window[-1].isoformat(),
        "groups": groups,
        "total": total,
        "pending": pending,
    }


# ---------- LLM 小贴士（可降级）----------

TIP_FALLBACK = "先吃菜再吃荤，六分饱收筷，今晚就不馋了。"


async def dinner_tip(recipe: Dict[str, Any]) -> str:
    """给今日晚餐生成 ≤30 字营养师小贴士；任何失败降级为模板文案。"""
    from server import ollama_client  # 延迟导入避免环

    try:
        resp = await asyncio.wait_for(
            ollama_client.agent_chat(
                [{"role": "user", "content": (
                    f"用不超过30个中文字，给减脂晚餐「{recipe['name']}」写一句营养师小贴士，"
                    "直接输出句子，不要解释。")}],
                tools=None,
            ),
            timeout=6,
        )
        text = (resp.get("content") or "").strip()
        if text:
            return text[:40]
    except Exception:  # noqa: BLE001 — 小贴士纯锦上添花，绝不影响主流程
        logger.info("晚餐小贴士生成失败，使用模板文案")
    return TIP_FALLBACK
