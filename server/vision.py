"""视觉识别管道：照片 → 结构化物品 JSON（中文直出，无翻译环节）。

qwen3-vl 中文直出，禁止引入第三个翻译模型。
"""

import json
import logging
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List

from server import ollama_client

logger = logging.getLogger("danshari.vision")

# 识别 prompt（写死中文模板）
VISION_PROMPT = (
    "你是家居整理助理。仔细看这张家庭照片，仅输出 JSON，不要输出其他文字：\n"
    '{"room":"推测区域(衣柜/客厅/厨房/书房/玄关/其他)",\n'
    ' "messiness":"low|medium|high",\n'
    ' "items":[{"name":"物品中文名","category":"clothing|book|kitchen|digital|toy|other",'
    '"quantity":数量}]}'
)

VALID_CATEGORIES = {"clothing", "book", "kitchen", "digital", "toy", "other"}
VALID_MESSINESS = {"low", "medium", "high"}


@dataclass
class VisionResult:
    """单张照片的结构化识别结果。"""

    room: str = "未知区域"
    messiness: str = "low"
    items: List[Dict[str, Any]] = field(default_factory=list)
    vision_text: str = ""      # 视觉模型原始输出（兜底存档）
    degraded: bool = False     # JSON 解析失败时降级为纯文本

    def to_summary(self) -> str:
        """供 Agent 消费的单行摘要。"""
        if self.degraded:
            return f"[视觉识别降级为原文] 区域:{self.room} 原文:{self.vision_text[:500]}"
        parts = [
            f"区域:{self.room}",
            f"混乱度:{self.messiness}",
            "物品:" + "、".join(
                f"{it['name']}×{it.get('quantity', 1)}({it.get('category', 'other')})"
                for it in self.items
            ),
        ]
        return " ".join(parts)


def _extract_json(text: str) -> Dict[str, Any]:
    """容错解析：可能带 markdown 代码块或多余文字，提取第一个 {...}。"""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)
    return json.loads(text)


def parse_vision_output(raw: str) -> VisionResult:
    """解析视觉模型输出；失败降级为纯文本（items 空，由 Needle 从原文提取）。"""
    try:
        data = _extract_json(raw)
    except (json.JSONDecodeError, AttributeError):
        logger.warning("视觉输出非 JSON，降级为纯文本：%s", raw[:200])
        return VisionResult(vision_text=raw, degraded=True)

    items: List[Dict[str, Any]] = []
    for it in data.get("items", []) or []:
        if not isinstance(it, dict) or not it.get("name"):
            continue
        category = it.get("category")
        if category not in VALID_CATEGORIES:
            category = "other"
        try:
            quantity = max(1, int(it.get("quantity") or 1))
        except (TypeError, ValueError):
            quantity = 1
        items.append(
            {"name": str(it["name"]), "category": category, "quantity": quantity}
        )

    messiness = data.get("messiness")
    if messiness not in VALID_MESSINESS:
        messiness = "low"

    return VisionResult(
        room=str(data.get("room") or "未知区域"),
        messiness=messiness,
        items=items,
        vision_text=raw,
    )


async def recognize(photo_bytes: bytes, room_hint: str = "") -> VisionResult:
    """单张照片 → 结构化结果。room_hint 为用户指定区域（优先于推断）。"""
    raw = await ollama_client.vision_generate([photo_bytes], VISION_PROMPT)
    result = parse_vision_output(raw)
    if room_hint:
        result.room = room_hint
    return result


# ---------- 命令行测试：python -m server.vision test.jpg ----------

def _main(argv: List[str]) -> int:
    logging.basicConfig(level=logging.INFO)
    import asyncio
    from pathlib import Path

    from server import db

    if not argv:
        print("用法: python -m server.vision <photo_id 或图片路径> [--mock]")
        return 2

    async def run() -> VisionResult:
        arg = argv[0]
        if arg.isdigit():
            db.get_conn()
            photo = db.get_photo(int(arg))
            if not photo:
                raise SystemExit(f"photo_id={arg} 不存在")
            img_path = db.DATA_DIR / photo["path"]
        else:
            img_path = Path(arg)
        raw = img_path.read_bytes()

        if "--mock" in argv or "mock" in argv:
            # 无 Ollama 时 mock 一段返回做联调
            mock = (
                '{"room":"衣柜","messiness":"high","items":['
                '{"name":"冬季外套","category":"clothing","quantity":3},'
                '{"name":"牛仔裤","category":"clothing","quantity":5},'
                '{"name":"旧毛衣","category":"clothing","quantity":2}]}'
            )
            return parse_vision_output(mock)

        return await recognize(raw)

    result = asyncio.run(run())
    print("room:", result.room)
    print("messiness:", result.messiness)
    print("items:", json.dumps(result.items, ensure_ascii=False, indent=2))
    print("degraded:", result.degraded)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
