"""SSE /api/chat 管道测试：mock 视觉识别与 Agent，验证事件流与落库。

运行：.venv/bin/python -m server.test_chat_pipeline（pytest 兼容）

覆盖此前缺失的最脆管道：_chat_stream 的 视觉→Agent→工具→plan_created→done 全链路，
以及视觉阶段报错时发 error+done 而不裸断流。
"""

import io
import json
import tempfile
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from PIL import Image

from server import db, ollama_client, vision
from server.main import app
from server.vision import VisionResult


def _fresh_db() -> Path:
    """全新临时库 + 临时照片目录（pipeline 按 db.DATA_DIR 相对路径读照片字节）。"""
    tmp = Path(tempfile.mkdtemp())
    db._conn = None
    db.DB_PATH = tmp / "test.db"
    db.DATA_DIR = tmp
    return tmp


def _tiny_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (180, 190, 170)).save(buf, format="JPEG")
    return buf.getvalue()


def _tool(name: str, args: dict) -> dict:
    return {"function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}


def _scripted_agent():
    """四轮脚本：save_items → judge_items → create_plan → 收尾文本。返回 (fake, calls)。"""
    calls = []

    async def fake(messages, tools=None):
        calls.append(messages)
        i = len(calls)
        if i == 1:
            return {"tool_calls": [_tool("save_items", {
                "photo_id": 1, "items": [{"name": "冬季外套", "category": "clothing", "quantity": 3}],
            })], "content": ""}
        if i == 2:
            return {"tool_calls": [_tool("judge_items", {"judgements": [
                {"name": "冬季外套", "keep_status": "keep", "reason": "常用"},
            ]})], "content": ""}
        if i == 3:
            return {"tool_calls": [_tool("create_plan", {"room": "衣柜", "summary": "收拾好了"})], "content": ""}
        return {"tool_calls": [], "content": "整理完成"}

    return fake, calls


def test_chat_pipeline_sse_full_flow() -> None:
    """照片→视觉→Agent→工具→plan_created→done 全链路，SSE 事件齐全且落库。"""
    tmp = _fresh_db()
    img_dir = tmp / "photos" / "2026-08-30"
    img_dir.mkdir(parents=True, exist_ok=True)
    (img_dir / "t.jpg").write_bytes(_tiny_jpeg())

    async def fake_recognize(photo_bytes, room_hint=""):
        return VisionResult(room="衣柜", messiness="high", items=[
            {"name": "冬季外套", "category": "clothing", "quantity": 3},
        ])

    fake_agent, _calls = _scripted_agent()
    with TestClient(app) as client, \
         mock.patch.object(vision, "recognize", fake_recognize), \
         mock.patch.object(ollama_client, "agent_chat", fake_agent):
        conv = db.create_conversation("管道测试")
        photo = db.create_photo("photos/2026-08-30/t.jpg")
        resp = client.get("/api/chat", params={
            "conversation_id": conv["id"],
            "message": "帮我整理",
            "photo_ids": str(photo["id"]),
        })
        body = resp.text

    assert resp.status_code == 200
    # SSE 事件流齐全
    assert "event: vision_done" in body
    assert "event: tool_call" in body
    assert "event: tool_result" in body
    assert "event: plan_created" in body
    assert "event: done" in body
    # 落库：物品 + 计划（计数后端聚合）+ 助手消息
    items = db.query_items()
    assert len(items) == 1 and items[0]["name"] == "冬季外套"
    plans = db.list_plans()
    assert len(plans) == 1
    assert plans[0]["keep_count"] == 3
    msgs = db.list_messages(conv["id"])
    assert any(m["role"] == "assistant" and "整理完成" in m["content"] for m in msgs)


def test_chat_pipeline_vision_error_emits_error_and_done() -> None:
    """视觉阶段抛异常：发 error 事件 + done 收尾，不裸断流、不写半截。"""
    tmp = _fresh_db()
    img_dir = tmp / "photos" / "2026-08-30"
    img_dir.mkdir(parents=True, exist_ok=True)
    (img_dir / "t.jpg").write_bytes(_tiny_jpeg())

    async def fake_recognize_broken(photo_bytes, room_hint=""):
        raise RuntimeError("模型超时")

    with TestClient(app) as client, \
         mock.patch.object(vision, "recognize", fake_recognize_broken):
        conv = db.create_conversation("管道报错")
        photo = db.create_photo("photos/2026-08-30/t.jpg")
        resp = client.get("/api/chat", params={
            "conversation_id": conv["id"],
            "message": "帮我整理",
            "photo_ids": str(photo["id"]),
        })
        body = resp.text

    assert "event: error" in body
    assert "event: done" in body
    # 没有半截助手总结落库（pipeline 在视觉阶段就 return）
    msgs = db.list_messages(conv["id"])
    assert not any(m["role"] == "assistant" for m in msgs)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all passed")
