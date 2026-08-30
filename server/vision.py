"""视觉识别管道：照片 → 结构化物品 JSON（中文直出，无翻译环节）。

qwen3-vl 中文直出，禁止引入第三个翻译模型。
"""

import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List

from server import ollama_client, rules

logger = logging.getLogger("danshari.vision")

# 识别 prompt（写死中文模板）——第一遍：全局扫描。
# 要点：逐一识别不合并、小物件不遗漏（knowledge/vision-enhancement/SKILL.md）
VISION_PROMPT = (
    "你是家居整理助理。仔细逐一看这张家庭照片，逐一识别每件物品，不要遗漏：\n"
    "- 不要把多件不同物品合并成“××衣物×N”这类粗分组；每件独立列出，用具体名称\n"
    "- 特别注意小物件和边缘角落：文具、工具、配件、护理用品等\n"
    "- 数量仅当物品完全相同（同款同类堆叠）时才>1\n"
    "仅输出 JSON，不要输出其他文字：\n"
    '{"room":"推测区域(衣柜/客厅/厨房/书房/玄关/其他)",\n'
    ' "messiness":"low|medium|high",\n'
    ' "items":[{"name":"物品中文名","category":"clothing|book|care|stationery|accessory|kitchen|digital|tool|toy|sports|other",'
    '"quantity":数量}]}'
)

# 第二遍：小物件专项补扫（vision-enhancement skill 核心机制）。
# 带第一遍结果，只报遗漏；新增项由上层标记为「待确认」。
SECOND_PASS_PROMPT = (
    "你是家居整理助理。第一遍识别已找出：{known_items}。\n"
    "请重新仔细检查这张照片，专门找第一遍遗漏的物品，重点是容易忽略的小物件：\n"
    "- 个人护理：梳子、发夹、皮筋、指甲剪、棉签、化妆刷等\n"
    "- 文具：笔、橡皮、回形针、便签、订书机、练习册等\n"
    "- 配件：钥匙、眼镜、耳机、充电线、U盘、卷尺等\n"
    "- 厨房小物：调料瓶、开瓶器、量勺、削皮器等\n"
    "- 其他小件：打火机、小工具、装饰品、药物等\n"
    "同时检查边缘、角落、容器内、被部分遮挡的物品。\n"
    "仅输出 JSON 数组（没有遗漏输出 []），不要输出其他文字：\n"
    '[{{"name":"物品中文名","category":"clothing|book|care|stationery|accessory|kitchen|digital|tool|toy|sports|other","quantity":数量}}]'
)

VALID_CATEGORIES = {"clothing", "book", "care", "stationery", "accessory", "kitchen", "digital", "tool", "toy", "sports", "other"}
VALID_MESSINESS = {"low", "medium", "high"}

# 二段式识别开关（本地 Ollama 速度慢时可关闭）
TWO_PASS_ENABLED = os.environ.get("VISION_TWO_PASS", "1") != "0"


@dataclass
class VisionResult:
    """单张照片的结构化识别结果。"""

    room: str = "未知区域"
    messiness: str = "low"
    items: List[Dict[str, Any]] = field(default_factory=list)
    suspected: List[Dict[str, Any]] = field(default_factory=list)  # 二遍新增待确认
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
        if self.suspected:
            parts.append(
                "待确认小物件:" + "、".join(
                    f"{it['name']}×{it.get('quantity', 1)}"
                    for it in self.suspected
                )
            )
        return " ".join(parts)


def _extract_json(text: str) -> Dict[str, Any]:
    """容错解析：剥 <think>/<answer> 标签，再提取 markdown 代码块或首个 {...}。"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"</?(?:answer|tool_call)>", "", text)
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


def merge_second_pass(base: List[Dict[str, Any]], extra: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """合并二遍结果：extra 中与 base 同名/包含关系的视为重复丢弃，其余为新增（待确认）。"""
    known = {rules.normalize_name(it["name"]) for it in base}
    added: List[Dict[str, Any]] = []
    for it in extra:
        n = rules.normalize_name(it["name"])
        # 双向包含："黑色上衣" vs "上衣"、"白色发夹" vs "黑色发夹"不匹配，"发夹" vs "发夹(3个)"匹配
        if any(n == k or (len(n) >= 2 and len(k) >= 2 and (n in k or k in n)) for k in known):
            continue
        known.add(n)
        added.append(it)
    return added


async def recognize(photo_bytes: bytes, room_hint: str = "") -> VisionResult:
    """单张照片 → 结构化结果。room_hint 为用户指定区域（优先于推断）。

    二段式（vision-enhancement skill）：
    ① 全局扫描 → 确认物品；② 小物件专项补扫 → 新增项进待确认列表。
    """
    raw = await ollama_client.vision_generate([photo_bytes], VISION_PROMPT)
    result = parse_vision_output(raw)
    if room_hint:
        result.room = room_hint

    if TWO_PASS_ENABLED and not result.degraded:
        try:
            known = "、".join(it["name"] for it in result.items) or "（无）"
            prompt = SECOND_PASS_PROMPT.replace("{known_items}", known)
            raw2 = await ollama_client.vision_generate([photo_bytes], prompt)
            extras = _parse_items_array(raw2)
            result.suspected = merge_second_pass(result.items, extras)
            if result.suspected:
                logger.info(
                    "二遍补扫新增待确认 %d 件：%s",
                    len(result.suspected),
                    "、".join(it["name"] for it in result.suspected),
                )
        except Exception:  # noqa: BLE001 — 二遍失败不影响一遍结果
            logger.warning("二遍补扫失败，降级为一遍结果", exc_info=True)

    # 存档：合并后的结构化 JSON（便于事后分析与回归）
    if not result.degraded:
        result.vision_text = json.dumps(
            {
                "room": result.room,
                "messiness": result.messiness,
                "items": result.items,
                "suspected": result.suspected,
            },
            ensure_ascii=False,
        )
    return result


def _parse_items_array(raw: str) -> List[Dict[str, Any]]:
    """解析二遍输出（JSON 数组），容错复用 _extract_json。"""
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        arr = re.search(r"\[.*\]", text, re.DOTALL)
        if arr:
            text = arr.group(0)
    data = json.loads(text)
    items: List[Dict[str, Any]] = []
    for it in data if isinstance(data, list) else []:
        if not isinstance(it, dict) or not it.get("name"):
            continue
        category = it.get("category")
        if category not in VALID_CATEGORIES:
            category = "other"
        try:
            quantity = max(1, int(it.get("quantity") or 1))
        except (TypeError, ValueError):
            quantity = 1
        items.append({"name": str(it["name"]), "category": category, "quantity": quantity})
    return items


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
    if result.suspected:
        print("suspected(待确认):", json.dumps(result.suspected, ensure_ascii=False, indent=2))
    print("degraded:", result.degraded)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
