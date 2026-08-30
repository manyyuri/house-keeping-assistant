"""Needle Agent 循环：标准 function calling，最多 5 轮防死循环（§7.1）。

messages = [system(断舍离顾问), 对话历史, 本轮用户消息+视觉JSON]
loop(max 5):
    resp = agent_chat(messages, TOOLS)
    if resp 无 tool_calls: break → 返回文本
    for call in resp.tool_calls:
        result = TOOL_IMPL[call.name](**args)   # 写库
        messages.append(assistant tool_calls)
        messages.append({role:"tool", name, content: json.dumps(result)})
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from server import ollama_client
from server.prompts import SYSTEM_PROMPT
from server.tools import TOOL_SCHEMAS, ToolContext, build_registry

logger = logging.getLogger("danshari.agent")

MAX_ROUNDS = 5

# 事件回调：异步推送 {type: "tool_call"|"tool_result"|"thought", ...}
EventCallback = Callable[[Dict[str, Any]], Awaitable[None]]


@dataclass
class AgentResult:
    text: str = ""
    tool_calls_log: List[Dict[str, Any]] = field(default_factory=list)


def _normalize_args(args: Any) -> Dict[str, Any]:
    """Ollama 可能返回 dict 或 JSON 字符串参数。"""
    if args is None or args == "":
        return {}
    if isinstance(args, dict):
        return args
    try:
        parsed = json.loads(args)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        logger.warning("工具参数解析失败：%r", args)
        return {}


def build_messages(
    history: List[Dict[str, Any]],
    user_content: str,
    vision_summaries: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """组装本轮 messages：system + 历史 + 用户消息（附视觉 JSON）。"""
    messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    content = user_content
    if vision_summaries:
        content += "\n\n[视觉识别结果（结构化）]\n" + "\n".join(vision_summaries)
    messages.append({"role": "user", "content": content})
    return messages


async def run_agent(
    messages: List[Dict[str, Any]],
    ctx: ToolContext,
    on_event: Optional[EventCallback] = None,
) -> AgentResult:
    """执行 Agent 循环。on_event 用于 SSE 推送 tool_call/tool_result。"""
    registry = build_registry(ctx)
    result = AgentResult()

    for _round in range(MAX_ROUNDS):
        resp = await ollama_client.agent_chat(messages, TOOL_SCHEMAS)
        tool_calls = resp.get("tool_calls") or []

        if not tool_calls:
            result.text = resp.get("content", "") or ""
            break

        # 记录 assistant 消息（含 tool_calls）供回填
        messages.append({"role": "assistant", "content": resp.get("content") or "", "tool_calls": tool_calls})

        for call in tool_calls:
            fn = (call.get("function") or {})
            name = fn.get("name", "")
            args = _normalize_args(fn.get("arguments"))
            result.tool_calls_log.append({"name": name, "args": args})

            if on_event:
                await on_event({"type": "tool_call", "name": name, "args": args})

            impl = registry.get(name)
            if impl is None:
                ret: Dict[str, Any] = {"ok": False, "error": f"未知工具: {name}"}
            else:
                try:
                    ret = impl(**args)
                except TypeError as e:
                    ret = {"ok": False, "error": f"参数不合法: {e}"}
                except Exception as e:  # noqa: BLE001 — 工具失败回填后由 Needle 告知用户
                    logger.exception("工具 %s 执行失败", name)
                    ret = {"ok": False, "error": str(e)}

            if on_event:
                await on_event({
                    "type": "tool_result", "name": name,
                    "ok": bool(ret.get("ok")),
                    "summary": _summarize_tool_result(name, ret),
                })

            messages.append({
                "role": "tool",
                "name": name,
                "content": json.dumps(ret, ensure_ascii=False),
            })
    else:
        logger.warning("Agent 达到最大轮数 %d，强制收尾", MAX_ROUNDS)
        if not result.text:
            result.text = "整理流程已执行完毕，如需继续细化请告诉我。"

    return result


def _summarize_tool_result(name: str, ret: Dict[str, Any]) -> str:
    """给 ThoughtChain 展示的一句话结果摘要。"""
    if not ret.get("ok"):
        return f"失败：{ret.get('error', '未知错误')}"
    if name == "save_items":
        saved = ret.get("saved", 0)
        deduped = ret.get("deduped")
        if deduped:
            return f"已入库 {saved} 件物品（同名合并 {deduped} 件）"
        return f"已入库 {saved} 件物品"
    if name == "judge_items":
        unmatched = ret.get("unmatched") or []
        extra = f"（{len(unmatched)} 件未匹配）" if unmatched else ""
        return f"已判定 {ret.get('updated', 0)} 件{extra}"
    if name == "create_plan":
        return (
            f"计划 #{ret.get('plan_id')} 已创建，断舍离评分 {ret.get('danshari_score')}"
            f"（丢 {ret.get('discard_count', 0)} / 捐 {ret.get('donate_count', 0)} / 留 {ret.get('keep_count', 0)}）"
        )
    if name == "create_tasks":
        return f"已创建 {ret.get('count', 0)} 个任务"
    if name == "query_items":
        return f"找到 {ret.get('total', 0)} 条相关物品"
    if name == "update_task_status":
        return f"任务 #{ret.get('task_id')} → {ret.get('status')}"
    if name == "get_today_meals":
        return f"已取回 {ret.get('date')} 三餐菜谱"
    if name == "reroll_meal":
        return f"{ret.get('meal_type')} 已换成「{ret.get('recipe')}」"
    return "完成"
