"""preferences 纯函数单测（忌口剔除 / 菜系偏好）+ seed 库与偏好一致性门禁。

运行：.venv/bin/python -m server.test_meal_prefs
"""

import json
from pathlib import Path

from server import preferences

SEED_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "recipes" / "recipes.json"


def _r(name: str, cuisine: str = "家常", food: str = "", ingredients=None) -> dict:
    return {
        "name": name,
        "cuisine": cuisine,
        "slots": [{"slot": "蔬菜", "kind": "veg", "fists": 2, "food": food}],
        "ingredients": ingredients or [],
    }


def test_allowed_default_neutral() -> None:
    """默认偏好（无忌口）→ 什么都能吃。"""
    prefs = preferences.DEFAULTS
    assert preferences.allowed(_r("随便一道", food="荷兰豆 300g"), prefs)
    assert preferences.allowed(_r("随便一道"), prefs)


def test_allowed_excludes_disliked_in_name() -> None:
    prefs = {"disliked_ingredients": ["荷兰豆"], "preferred_cuisines": []}
    assert not preferences.allowed(_r("白灼虾 + 清炒荷兰豆", food="荷兰豆 300g"), prefs)
    assert not preferences.allowed(_r("荷兰豆牛柳饭"), prefs)


def test_allowed_excludes_disliked_in_ingredients() -> None:
    """忌口命中用料名（不只是菜名）。"""
    prefs = {"disliked_ingredients": ["香菜"], "preferred_cuisines": []}
    r = _r("牛肉饭", ingredients=[{"name": "香菜", "amount": "1 把"}])
    assert not preferences.allowed(r, prefs)


def test_allowed_partial_dislike_only_blocks_matching() -> None:
    prefs = {"disliked_ingredients": ["荷兰豆"], "preferred_cuisines": []}
    assert preferences.allowed(_r("清蒸鲈鱼套餐", food="鲈鱼"), prefs)


def test_favored_by_cuisine() -> None:
    prefs = {"disliked_ingredients": [], "preferred_cuisines": ["川菜", "韩餐"]}
    assert preferences.favored(_r("水煮鱼", cuisine="川菜"), prefs)
    assert preferences.favored(_r("辣炒鱿鱼", cuisine="韩餐"), prefs)
    assert not preferences.favored(_r("清蒸鲈鱼", cuisine="粤菜"), prefs)
    assert not preferences.favored(_r("家常菜", cuisine="家常"), prefs)


def test_split_pool() -> None:
    prefs = {"disliked_ingredients": ["荷兰豆"], "preferred_cuisines": ["粤菜"]}
    pool = [
        _r("a", cuisine="粤菜", food="芦笋 300g"),
        _r("b", cuisine="家常", food="荷兰豆 300g"),  # 忌口，剔除
        _r("c", cuisine="川菜", food="莴笋 300g"),    # 可吃但非偏好
        _r("d", cuisine="粤菜", food="菜心 400g"),
    ]
    eat, fav = preferences.split_pool(pool, prefs)
    assert [r["name"] for r in eat] == ["a", "c", "d"]
    assert [r["name"] for r in fav] == ["a", "d"]


def test_seed_no_disliked_left_and_has_favored() -> None:
    """库与用户偏好对齐的门禁：seed 已无荷兰豆/芥蓝/鱼香；川/粤/韩/日都有在库。"""
    rows = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    prefs = {
        "disliked_ingredients": ["荷兰豆", "芥蓝", "鱼香"],
        "preferred_cuisines": ["川菜", "粤菜", "韩餐", "日料"],
    }
    assert not any(
        not preferences.allowed(r, prefs) for r in rows
    ), "seed 库仍含有忌口食材（荷兰豆/芥蓝/鱼香）"
    cuisines = {r.get("cuisine") for r in rows}
    for fav in prefs["preferred_cuisines"]:
        assert fav in cuisines, f"偏好菜系 {fav} 在 seed 库里一道也没有"


if __name__ == "__main__":
    import sys

    # 允许指定用例名：python -m server.test_meal_prefs test_favored_by_cuisine
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            if only and only != name:
                continue
            fn()
            print(f"PASS {name}")
    print("all passed")
