"""Needle Agent 工具定义与实现（写 SQLite，一律返回 {"ok":true,...} 供续写）。

八个工具（§7.2 + 三餐）：
  save_items / judge_items / create_plan / create_tasks / query_items /
  update_task_status / get_today_meals / reroll_meal
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from server import db, meals, rules

logger = logging.getLogger("danshari.tools")

VALID_KEEP_STATUS = {"keep", "donate", "discard", "hesitate"}

# Ollama tools JSON Schema 数组
TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "save_items",
            "description": (
                "将视觉识别出的物品批量入库（keep_status=unjudged）。"
                "用户上传照片后必须最先调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "photo_id": {"type": "integer", "description": "照片 id"},
                    "items": {
                        "type": "array",
                        "description": "物品列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "物品中文名"},
                                "category": {
                                    "type": "string",
                                    "enum": ["clothing", "book", "kitchen", "digital", "toy", "other"],
                                },
                                "quantity": {"type": "integer", "minimum": 1},
                            },
                            "required": ["name", "category", "quantity"],
                        },
                    },
                },
                "required": ["photo_id", "items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "judge_items",
            "description": (
                "按三层筛子对物品逐件判定（keep保留/donate捐赠/discard丢弃/hesitate犹豫），"
                "理由必须写入 reason。hesitate 自动进入 90 天观察期。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "judgements": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "物品名（模糊匹配）"},
                                "keep_status": {"type": "string", "enum": ["keep", "donate", "discard", "hesitate"]},
                                "reason": {"type": "string", "description": "判定理由（必要/合适/愉快 三问结论）"},
                            },
                            "required": ["name", "keep_status", "reason"],
                        },
                    }
                },
                "required": ["judgements"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_plan",
            "description": "创建整理计划。danshari_score 与丢/捐/留计数都由系统按规则与物品库实时计算，勿自行编造。",
            "parameters": {
                "type": "object",
                "properties": {
                    "room": {"type": "string", "description": "区域，如 衣柜/客厅/厨房"},
                    "summary": {"type": "string", "description": "一句话结论（含加分法肯定）"},
                    "discard_count": {"type": "integer"},
                    "donate_count": {"type": "integer"},
                    "keep_count": {"type": "integer"},
                },
                "required": ["room", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_tasks",
            "description": (
                "为计划拆解任务。顺序铁则：先取舍(discard)、后收纳(store)、再清扫(clean)。"
                "必须包含'今日15分钟'与'周末60分钟'两档。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "integer"},
                    "tasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": ["clean", "organize", "store", "discard"]},
                                "title": {"type": "string"},
                                "steps": {"type": "array", "items": {"type": "string"}, "description": "2-5 个具体步骤"},
                                "est_minutes": {"type": "integer"},
                                "due_date": {"type": "string", "description": "建议日期 yyyy-mm-dd 或 today/weekend"},
                            },
                            "required": ["type", "title", "steps", "est_minutes"],
                        },
                    },
                },
                "required": ["plan_id", "tasks"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_items",
            "description": "按关键词查询物品库存（含 keep_status 与观察期），回答'我还有几条牛仔裤'类问题。",
            "parameters": {
                "type": "object",
                "properties": {"keyword": {"type": "string"}},
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task_status",
            "description": "更新任务状态（todo/doing/done/skipped），对话中也能勾任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer"},
                    "status": {"type": "string", "enum": ["todo", "doing", "done", "skipped"]},
                },
                "required": ["task_id", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_today_meals",
            "description": (
                "查询三餐菜谱（默认今天，可传 yyyy-mm-dd）。含每餐菜名、拳头份量、"
                "食材、Cook5 用时、便当信息；回答“今天吃什么/买菜清单”类问题。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "日期 yyyy-mm-dd，缺省为今天"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reroll_meal",
            "description": (
                "换一餐的菜（breakfast/lunch/dinner），自动同步盒马买菜清单。"
                "便当已在制作日（前一天）19:00 后做好时会被拒绝。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "meal_type": {"type": "string", "enum": ["breakfast", "lunch", "dinner"]},
                    "date": {"type": "string", "description": "日期 yyyy-mm-dd，缺省为今天"},
                },
                "required": ["meal_type"],
            },
        },
    },
]


@dataclass
class ToolContext:
    """一次对话轮的工具执行上下文（供 create_plan 计算评分等）。"""

    conversation_id: Optional[int] = None
    photo_ids: List[int] = field(default_factory=list)
    messiness: str = "low"
    # create_plan 执行后回填，供 SSE 层推送 plan_created 事件
    last_plan: Optional[Dict[str, Any]] = None


def tool_save_items(photo_id: int, items: List[Dict[str, Any]], ctx: ToolContext) -> Dict[str, Any]:
    """批量入 items 表（unjudged）。photo_id 无效时挂 None（仍可入库）。

    同名物品在同一张照片内自动合并（稳定身份，见 db.save_items）。
    """
    cleaned = [
        {
            "name": str(it.get("name") or "未命名物品"),
            "category": it.get("category") or "other",
            "quantity": max(1, int(it.get("quantity") or 1)),
        }
        for it in items
        if isinstance(it, dict) and it.get("name")
    ]
    if not cleaned:
        return {"ok": False, "error": "items 为空"}
    pid = photo_id if (photo_id and db.get_photo(photo_id)) else None
    res = db.save_items(pid, cleaned)
    if pid and pid not in ctx.photo_ids:
        ctx.photo_ids.append(pid)
    return {"ok": True, "saved": res["saved"], "deduped": res["deduped"], "count": len(cleaned)}


def tool_judge_items(judgements: List[Dict[str, Any]], ctx: ToolContext) -> Dict[str, Any]:
    """按 name 判定 keep_status/reason；hesitate 自动 +90 天观察期。

    稳定身份：先按归一化名精确匹配（"冬季外套"判到"冬季外套(3件)"），
    同批同类统一判定；无精确匹配才退回 LIKE 候选，且无批次上下文时保守只改首条，
    绝不静默改到与名字无关的行。返回 matched（改到哪几行，可追溯）。
    """
    updated = 0
    unmatched: List[str] = []
    matched: List[Dict[str, Any]] = []
    for j in judgements:
        name = str(j.get("name") or "").strip()
        status = j.get("keep_status")
        if not name or status not in VALID_KEEP_STATUS:
            continue
        norm = rules.normalize_name(name)
        candidates = db.query_items(keyword=name)
        if ctx.photo_ids:
            # 优先本轮照片关联的物品
            own = [c for c in candidates if c["photo_id"] in ctx.photo_ids]
            candidates = own or candidates
        exact = [c for c in candidates if rules.normalize_name(c["name"]) == norm]
        if exact:
            pool = exact
        elif ctx.photo_ids:
            pool = candidates  # 批次内：同类统一判定
        else:
            pool = candidates[:1]  # 无批次上下文：保守只改首条，避免误伤历史
        if not pool:
            unmatched.append(name)
            continue
        quarantine = rules.quarantine_until_today() if status == "hesitate" else None
        for c in pool:
            db.update_item(
                c["id"], keep_status=status, reason=j.get("reason"), quarantine_until=quarantine
            )
            matched.append({"id": c["id"], "name": c["name"]})
            updated += 1
    return {"ok": True, "updated": updated, "unmatched": unmatched, "matched": matched}


def tool_create_plan(
    room: str,
    summary: str,
    discard_count: int = 0,
    donate_count: int = 0,
    keep_count: int = 0,
    ctx: ToolContext = None,
) -> Dict[str, Any]:
    """创建计划。danshari_score 一律由 rules.py 计算——不信任 Needle 自报分数。

    计数（丢/捐/留）同样由 items 表实时聚合——不信任 Needle 自报计数（与评分同哲学）：
    一个计划只讲一套可信的数字，避免 LLM 编的 counts 与规则算的 score 同屏打架。
    """
    ctx = ctx or ToolContext()
    items: List[Dict[str, Any]] = []
    for pid in ctx.photo_ids:
        items.extend(db.query_items(photo_id=pid))
    if not items:
        # 无照片关联时退化为全库未判定+已判定物品（查询类对话）
        items = db.query_items()
    score = rules.danshari_score(items, messiness=ctx.messiness)
    counts = {"discard": 0, "donate": 0, "keep": 0}
    for it in items:
        st = it.get("keep_status")
        if st in counts:
            counts[st] += int(it.get("quantity") or 1)
    plan = db.create_plan(
        room=room,
        summary=summary,
        danshari_score=score,
        discard_count=counts["discard"],
        donate_count=counts["donate"],
        keep_count=counts["keep"],
        conversation_id=ctx.conversation_id,
        photo_ids=ctx.photo_ids,
    )
    ctx.last_plan = {"plan_id": plan["id"], "danshari_score": score,
                     "task_count": len(db.list_tasks(plan_id=plan["id"]))}
    return {"ok": True, "plan_id": plan["id"], "danshari_score": score,
            "grade": rules.score_grade(score), **counts}


def tool_create_tasks(plan_id: int, tasks: List[Dict[str, Any]], ctx: ToolContext) -> Dict[str, Any]:
    plan = db.get_plan(plan_id)
    if not plan:
        return {"ok": False, "error": f"plan_id={plan_id} 不存在，请先 create_plan"}
    cleaned = []
    for t in tasks:
        if not isinstance(t, dict) or not t.get("title"):
            continue
        cleaned.append({
            "type": t.get("type") if t.get("type") in ("clean", "organize", "store", "discard") else "organize",
            "title": str(t["title"]),
            "steps": [str(s) for s in (t.get("steps") or [])][:5],
            "est_minutes": t.get("est_minutes"),
            "due_date": t.get("due_date"),
        })
    if not cleaned:
        return {"ok": False, "error": "tasks 为空"}
    ids = db.create_tasks(plan_id, cleaned)
    if ctx.last_plan and ctx.last_plan.get("plan_id") == plan_id:
        ctx.last_plan["task_count"] = len(ids)
    return {"ok": True, "task_ids": ids, "count": len(ids)}


def tool_query_items(keyword: str, ctx: ToolContext) -> Dict[str, Any]:
    rows = db.query_items(keyword=keyword)
    return {
        "ok": True,
        "keyword": keyword,
        "total": len(rows),
        "total_quantity": sum(r["quantity"] for r in rows),
        "items": [
            {
                "id": r["id"], "name": r["name"], "quantity": r["quantity"],
                "keep_status": r["keep_status"], "quarantine_until": r["quarantine_until"],
            }
            for r in rows[:20]
        ],
    }


def tool_update_task_status(task_id: int, status: str, ctx: ToolContext) -> Dict[str, Any]:
    if status not in ("todo", "doing", "done", "skipped"):
        return {"ok": False, "error": f"非法 status: {status}"}
    task = db.update_task_status(task_id, status)
    if not task:
        return {"ok": False, "error": f"task_id={task_id} 不存在"}
    return {"ok": True, "task_id": task_id, "status": status}


def tool_get_today_meals(date: Optional[str], ctx: ToolContext) -> Dict[str, Any]:
    """查询三餐（无则幂等生成）；返回精简菜谱供 Agent 复述，菜单由规则引擎保证。"""
    try:
        day = meals.ensure_day(date)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    out_meals = {}
    for mt, p in day["meals"].items():
        r = (p or {}).get("recipe") or {}
        out_meals[mt] = {
            "name": r.get("name"),
            "mode": p.get("mode"),
            "status": p.get("status"),
            "fists": [f"{s['slot']}{s['fists']}拳" for s in r.get("slots", [])],
            "ingredients": [f"{i['name']} {i['amount']}" for i in r.get("ingredients", [])],
            "cook": f"{r.get('cook_tool')} {r.get('cook_minutes') or ''}分钟".strip(),
        }
    out = {"ok": True, "date": day["date"], "weekday": day["weekday"], "meals": out_meals}
    dinner = day["meals"].get("dinner") or {}
    if dinner.get("bento_preview"):
        out["bento_preview"] = dinner["bento_preview"]
    return out


def tool_reroll_meal(meal_type: str, date: Optional[str], ctx: ToolContext) -> Dict[str, Any]:
    if meal_type not in meals.MEAL_ORDER:
        return {"ok": False, "error": "meal_type 必须为 breakfast/lunch/dinner"}
    try:
        plan = meals.reroll(date, meal_type)
    except meals.BentoLocked:
        return {"ok": False, "error": "便当昨晚已做好，无法换菜", "bento_locked": True}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    r = plan["recipe"] or {}
    return {
        "ok": True,
        "date": plan["plan_date"],
        "meal_type": meal_type,
        "recipe": r.get("name"),
        "cook_minutes": r.get("cook_minutes"),
        "note": "买菜清单已同步更新",
    }


def build_registry(ctx: ToolContext) -> Dict[str, Callable[..., Dict[str, Any]]]:
    """绑定 ToolContext 的工具注册表。"""

    def save_items(photo_id: int, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        return tool_save_items(photo_id, items, ctx)

    def judge_items(judgements: List[Dict[str, Any]]) -> Dict[str, Any]:
        return tool_judge_items(judgements, ctx)

    def create_plan(room: str, summary: str, discard_count: int = 0,
                    donate_count: int = 0, keep_count: int = 0) -> Dict[str, Any]:
        return tool_create_plan(room, summary, discard_count, donate_count, keep_count, ctx)

    def create_tasks(plan_id: int, tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
        return tool_create_tasks(plan_id, tasks, ctx)

    def query_items(keyword: str) -> Dict[str, Any]:
        return tool_query_items(keyword, ctx)

    def update_task_status(task_id: int, status: str) -> Dict[str, Any]:
        return tool_update_task_status(task_id, status, ctx)

    def get_today_meals(date: Optional[str] = None) -> Dict[str, Any]:
        return tool_get_today_meals(date, ctx)

    def reroll_meal(meal_type: str, date: Optional[str] = None) -> Dict[str, Any]:
        return tool_reroll_meal(meal_type, date, ctx)

    return {
        "save_items": save_items,
        "judge_items": judge_items,
        "create_plan": create_plan,
        "create_tasks": create_tasks,
        "query_items": query_items,
        "update_task_status": update_task_status,
        "get_today_meals": get_today_meals,
        "reroll_meal": reroll_meal,
    }
