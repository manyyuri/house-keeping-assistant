"""agent.py 循环测试：mock ollama_client.agent_chat，验证工具调用→写库→收尾。

运行：.venv/bin/python -m server.test_agent（pytest 兼容）

覆盖此前缺失的最脆逻辑：tool_calls 循环、tool_call_id 回填后的消息链、
ToolContext.last_plan 回填、未知工具错误回填、MAX_ROUNDS 强制收尾。
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest import mock

from server import agent, db, ollama_client
from server.agent import MAX_ROUNDS
from server.tools import ToolContext


def _run_agent(messages, ctx):
    """asyncio 驱动 run_agent（agent_chat 已被 mock 为 async 函数）。"""
    return asyncio.run(agent.run_agent(messages, ctx))


def _fresh_db() -> Path:
    """让 db 模块指向全新的临时库（须在首次 get_conn 之前替换 DB_PATH）。"""
    tmp = Path(tempfile.mkdtemp()) / "test.db"
    db._conn = None
    db.DB_PATH = tmp
    return tmp


def _photo() -> int:
    return db.create_photo("photos/test/a.jpg")["id"]


def _tool(name: str, args: dict) -> dict:
    return {"function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}


def _scripted(*responses):
    """按顺序返回脚本化响应的 agent_chat mock；耗尽后复用末个（防越界）。"""
    it = iter(responses)

    async def fake(messages, tools=None):
        try:
            return next(it)
        except StopIteration:
            return responses[-1]

    return fake


def test_agent_full_flow_saves_judges_plans_tasks() -> None:
    """全流程：save_items→judge_items→create_plan→create_tasks→收尾文本。"""
    _fresh_db()
    pid = _photo()
    conv = db.create_conversation("agent 全流程")
    script = [
        {"tool_calls": [_tool("save_items", {"photo_id": pid, "items": [
            {"name": "冬季外套", "category": "clothing", "quantity": 3},
            {"name": "旧毛衣", "category": "clothing", "quantity": 1},
        ]})], "content": ""},
        {"tool_calls": [_tool("judge_items", {"judgements": [
            {"name": "冬季外套", "keep_status": "keep", "reason": "常用"},
            {"name": "旧毛衣", "keep_status": "discard", "reason": "变形"},
        ]})], "content": ""},
        {"tool_calls": [_tool("create_plan", {"room": "衣柜", "summary": "收拾好了"})], "content": ""},
        {"tool_calls": [_tool("create_tasks", {"plan_id": 1, "tasks": [
            {"type": "discard", "title": "捐旧毛衣", "steps": ["装袋"], "est_minutes": 10},
        ]})], "content": ""},
        {"tool_calls": [], "content": "全部完成"},
    ]
    with mock.patch.object(ollama_client, "agent_chat", _scripted(*script)):
        ctx = ToolContext(conversation_id=conv["id"], photo_ids=[pid], messiness="high")
        messages = agent.build_messages([], "帮我整理衣柜", [])
        result = _run_agent(messages, ctx)

    assert result.text == "全部完成"
    # 物品已入库并判定
    items = db.query_items()
    by_name = {i["name"]: i for i in items}
    assert by_name["冬季外套"]["keep_status"] == "keep"
    assert by_name["旧毛衣"]["keep_status"] == "discard"
    # 计划：计数来自后端聚合（丢弃1 / 保留3），不信任 LLM 自报
    plans = db.list_plans()
    assert len(plans) == 1
    assert plans[0]["room"] == "衣柜"
    assert plans[0]["discard_count"] == 1
    assert plans[0]["keep_count"] == 3
    assert plans[0]["donate_count"] == 0
    # last_plan 回填（SSE plan_created 依赖）
    assert ctx.last_plan and ctx.last_plan["plan_id"] == plans[0]["id"]
    # 任务
    tasks = db.list_tasks(plan_id=plans[0]["id"])
    assert len(tasks) == 1 and tasks[0]["title"] == "捐旧毛衣"


def test_agent_unknown_tool_error_fed_back() -> None:
    """未知工具：错误回填给模型，循环继续，不中断。"""
    _fresh_db()
    conv = db.create_conversation("未知工具")
    script = [
        {"tool_calls": [_tool("no_such_tool", {})], "content": ""},
        {"tool_calls": [], "content": "未知工具已忽略"},
    ]
    with mock.patch.object(ollama_client, "agent_chat", _scripted(*script)):
        ctx = ToolContext(conversation_id=conv["id"])
        result = _run_agent(agent.build_messages([], "hi", []), ctx)

    assert result.text == "未知工具已忽略"
    assert result.tool_calls_log[0]["name"] == "no_such_tool"


def test_agent_force_stop_after_max_rounds() -> None:
    """模型一直要求调工具：MAX_ROUNDS 后强制收尾，绝不无限循环。"""
    _fresh_db()
    conv = db.create_conversation("无限工具循环")
    always = {"tool_calls": [_tool("query_items", {"keyword": "x"})], "content": ""}
    with mock.patch.object(ollama_client, "agent_chat", _scripted(always)):
        ctx = ToolContext(conversation_id=conv["id"])
        result = _run_agent(agent.build_messages([], "hi", []), ctx)

    assert len(result.tool_calls_log) == MAX_ROUNDS  # 不超上限
    assert result.text  # 兜底收尾文案


def test_save_items_dedupes_by_normalized_name() -> None:
    """稳定身份：同一照片内同名合并（\"冬季外套(3件)\" 与 \"冬季外套\" 归一化一致）。"""
    _fresh_db()
    pid = _photo()
    db.save_items(pid, [{"name": "冬季外套", "category": "clothing", "quantity": 3}])
    res = db.save_items(pid, [{"name": "冬季外套", "category": "clothing", "quantity": 2}])
    assert res["saved"] == 2 and res["deduped"] == 2
    rows = db.query_items(photo_id=pid)
    assert len(rows) == 1 and rows[0]["quantity"] == 5


def test_score_penalizes_unresolved_and_zero_discard() -> None:
    """P0 评分语义：代谢率——该舍未舍（高混乱却零丢弃）与未决物品必须扣分，全 keep 不得满分。"""
    from server import rules

    # 高混乱 + 全 keep：混乱15 + 红警10 + 同类超量4*(5-2)=12 → 远低于 100
    messy_keep_all = [{"name": "杂物", "category": "other", "quantity": 5, "keep_status": "keep"}]
    assert rules.danshari_score(messy_keep_all, messiness="high") == 100 - 15 - 10 - 12

    # 未决物品：每件 -3（三层筛子没走完）
    unjudged = [{"name": "a", "category": "other", "quantity": 2, "keep_status": "unjudged"}]
    assert rules.danshari_score(unjudged, messiness="low") == 100 - 3 * 2

    # 低混乱 + 正常判定：红警只在高/中混乱触发，整洁房间不误伤
    tidy = [{"name": "a", "category": "other", "quantity": 1, "keep_status": "keep"}]
    assert rules.danshari_score(tidy, messiness="low") == 100

    # 该舍未舍但混乱度中：红警 -5
    medium = [{"name": "a", "category": "other", "quantity": 1, "keep_status": "keep"}]
    assert rules.danshari_score(medium, messiness="medium") == 100 - 8 - 5


def test_judge_items_stable_identity_same_batch() -> None:
    """稳定身份：judge 按归一化名判到全部同批同名行，不静默只改首行。"""
    _fresh_db()
    pid = _photo()
    db.save_items(pid, [
        {"name": "黑色上衣", "category": "clothing", "quantity": 1},
        {"name": "白色上衣", "category": "clothing", "quantity": 1},
    ])
    ctx = ToolContext(photo_ids=[pid])
    ret = tool_judge_items_pub([{"name": "上衣", "keep_status": "discard", "reason": "变形"}], ctx)
    assert ret["ok"] and ret["updated"] == 2
    rows = db.query_items(photo_id=pid)
    assert {r["keep_status"] for r in rows} == {"discard"}


def tool_judge_items_pub(judgements, ctx):
    """测试入口：直接调实现（与 build_registry 同路径）。"""
    from server.tools import tool_judge_items

    return tool_judge_items(judgements, ctx)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all passed")
