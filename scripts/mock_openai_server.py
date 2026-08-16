"""Mock OpenAI 兼容服务——无真实 API key 的全链路联调（httpx 不走系统代理）。

行为（POST */chat/completions，兼容任意 base_url 前缀）：
- Authorization 非 `Bearer sk-good*` → 401（验证错误映射）
- 消息含 image_url 内容块（视觉请求）→ 返回固定 VISION_JSON（与衣柜场景一致）
- 带 tools 的 Agent 请求按 messages 中 role:"tool" 数量编排：
  - 0 个 → 第 1 轮：save_items + judge_items + create_plan 三连 tool_calls
  - ≥1 个 → 收尾文本（约 180 字，SSE 分 3 段 message_delta）
- 其余（测试连接 hi/test）→ "ok"

启动：
    .venv/bin/python scripts/mock_openai_server.py            # 默认 127.0.0.1:9101
    .venv/bin/python scripts/mock_openai_server.py 9101
"""

import sys
from typing import Any, Dict, List

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="mock-openai")

VISION_JSON = (
    '{"room":"衣柜","messiness":"high","items":['
    '{"name":"冬季外套","category":"clothing","quantity":3},'
    '{"name":"牛仔裤","category":"clothing","quantity":5},'
    '{"name":"旧毛衣","category":"clothing","quantity":2}]}'
)

FINAL_TEXT = (
    "衣柜整体评估完成：10 件衣物中建议保留 3 件冬季外套（今年高频穿着），"
    "捐赠 5 条牛仔裤（近两年未穿、尺码不合），丢弃 2 件起球旧毛衣（无法捐赠）。"
    "断舍离评分已按规则计算入库，任务清单按「先取舍、后收纳、再清扫」排序："
    "今日先完成 15 分钟三袋法清空，周末 60 分钟完成分区收纳与复查。"
    "坚持一件进一件出的原则，衣柜只留必要、合适、愉快的物品。"
)


def _tool_call(index: int, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    import json

    return {
        "id": f"call_{index}_{name}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }


def _completion(message: Dict[str, Any], finish_reason: str = "stop") -> Dict[str, Any]:
    return {
        "id": "chatcmpl-mock",
        "model": "mock",
        "choices": [{"index": 0, "finish_reason": finish_reason, "message": message}],
        "usage": {"total_tokens": 64},
    }


def _has_image(messages: List[Dict[str, Any]]) -> bool:
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            if any(isinstance(b, dict) and b.get("type") == "image_url" for b in content):
                return True
    return False


def _tool_msg_count(messages: List[Dict[str, Any]]) -> int:
    return sum(1 for m in messages if m.get("role") == "tool")


@app.post("/{path:path}")
async def chat_completions(path: str, request: Request) -> Any:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer sk-good"):
        return JSONResponse({"error": {"message": "Invalid API key"}}, status_code=401)

    body = await request.json()
    messages: List[Dict[str, Any]] = body.get("messages") or []

    if body.get("tools"):
        if _tool_msg_count(messages) == 0:
            return _completion(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        _tool_call(0, "save_items", {
                            "photo_id": 1,
                            "items": [
                                {"name": "冬季外套", "category": "clothing", "quantity": 3},
                                {"name": "牛仔裤", "category": "clothing", "quantity": 5},
                                {"name": "旧毛衣", "category": "clothing", "quantity": 2},
                            ],
                        }),
                        _tool_call(1, "judge_items", {
                            "judgements": [
                                {"name": "冬季外套", "keep_status": "keep", "reason": "今年冬天常穿，必要且合适"},
                                {"name": "牛仔裤", "keep_status": "donate", "reason": "两年未穿，尺码不合"},
                                {"name": "旧毛衣", "keep_status": "discard", "reason": "起球变形，无法捐赠"},
                            ],
                        }),
                        _tool_call(2, "create_plan", {
                            "room": "衣柜",
                            "summary": "衣柜过载：先舍后纳，保留高频衣物",
                            "discard_count": 2,
                            "donate_count": 5,
                            "keep_count": 3,
                        }),
                    ],
                },
                finish_reason="tool_calls",
            )
        return _completion({"role": "assistant", "content": FINAL_TEXT})

    if _has_image(messages):
        return _completion({"role": "assistant", "content": VISION_JSON})

    return _completion({"role": "assistant", "content": "ok"})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9101
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
