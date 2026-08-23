"""vision.py 纯函数回归测试（不联网）。

运行：.venv/bin/python -m server.test_vision
"""

import json

from server.vision import (
    SECOND_PASS_PROMPT,
    _parse_items_array,
    merge_second_pass,
    parse_vision_output,
)


def test_parse_vision_output_basic() -> None:
    raw = (
        '```json\n{"room":"书房","messiness":"medium","items":['
        '{"name":"书法练习册","category":"stationery","quantity":2},'
        '{"name":"卷尺","category":"tool","quantity":1},'
        '{"name":"未知类目","category":"weird","quantity":3}]}'
    )
    r = parse_vision_output(raw)
    assert r.room == "书房"
    assert r.messiness == "medium"
    assert [it["name"] for it in r.items] == ["书法练习册", "卷尺", "未知类目"]
    assert r.items[2]["category"] == "other"  # 非法类目回退
    assert r.items[0]["quantity"] == 2
    assert not r.degraded


def test_parse_vision_output_degraded() -> None:
    r = parse_vision_output("这不是JSON")
    assert r.degraded
    assert r.items == []


def test_parse_items_array_with_think_and_fence() -> None:
    raw = (
        "<think>让我想想…</think>\n"
        "```json\n[{\"name\":\"木梳\",\"category\":\"care\",\"quantity\":1},"
        "{\"name\":\"发夹（3个）\",\"category\":\"care\",\"quantity\":3}]\n```"
    )
    items = _parse_items_array(raw)
    assert [it["name"] for it in items] == ["木梳", "发夹（3个）"]
    assert items[0]["category"] == "care"
    assert items[1]["quantity"] == 3


def test_parse_items_array_empty() -> None:
    assert _parse_items_array("[]") == []
    assert _parse_items_array("没有遗漏 [] ") == []


def test_merge_second_pass_dedup() -> None:
    base = [
        {"name": "黑色上衣", "category": "clothing", "quantity": 1},
        {"name": "行李箱", "category": "other", "quantity": 1},
    ]
    extra = [
        {"name": "上衣", "category": "clothing", "quantity": 1},        # 包含重复
        {"name": "行李箱（2个）", "category": "other", "quantity": 2},  # 归一化重复
        {"name": "卷尺", "category": "tool", "quantity": 1},           # 新增
    ]
    added = merge_second_pass(base, extra)
    assert [it["name"] for it in added] == ["卷尺"]


def test_merge_second_pass_distinct_colors_not_merged() -> None:
    base = [{"name": "黑色发夹", "category": "care", "quantity": 1}]
    extra = [{"name": "白色发夹", "category": "care", "quantity": 2}]
    added = merge_second_pass(base, extra)
    assert len(added) == 1  # 不同颜色=不同物品，不合并


def test_summary_contains_suspected() -> None:
    from server.vision import VisionResult

    r = VisionResult(
        room="衣柜",
        messiness="high",
        items=[{"name": "外套", "category": "clothing", "quantity": 1}],
        suspected=[{"name": "卷尺", "category": "tool", "quantity": 1}],
    )
    s = r.to_summary()
    assert "待确认小物件:卷尺×1" in s
    assert "物品:外套×1(clothing)" in s


def test_second_pass_prompt_has_known_slot() -> None:
    assert "{known_items}" in SECOND_PASS_PROMPT


def test_vision_text_archive_format() -> None:
    """确认存档 JSON 结构（update_photo_vision 落库内容）。"""
    from server.vision import VisionResult

    r = VisionResult(room="书房", messiness="low", items=[], suspected=[])
    archived = json.loads(
        json.dumps(
            {"room": r.room, "messiness": r.messiness, "items": r.items, "suspected": r.suspected},
            ensure_ascii=False,
        )
    )
    assert archived["suspected"] == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")
