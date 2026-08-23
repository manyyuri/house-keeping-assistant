"""meal_rules 纯函数单测（无 IO、无 LLM 依赖）。

运行：.venv/bin/python -m server.test_meal_rules
"""

from server import meal_rules


def _slot(slot: str, kind: str, fists: int) -> dict:
    return {"slot": slot, "kind": kind, "fists": fists, "food": "x"}


def test_validate_breakfast_ok() -> None:
    slots = [
        _slot("粗粮", "staple", 1),
        _slot("蛋奶", "protein", 1),
        _slot("蔬果", "veg", 1),
    ]
    ok, problems = meal_rules.validate_meal("breakfast", slots)
    assert ok and problems == []


def test_validate_dinner_rejects_staple() -> None:
    """晚餐模板无主食：加主食（减脂约束）必须报错。"""
    slots = [
        _slot("蔬菜", "veg", 2),
        _slot("主食", "staple", 1),
        _slot("鱼虾贝", "seafood", 1),
    ]
    ok, problems = meal_rules.validate_meal("dinner", slots)
    assert not ok and problems


def test_validate_lunch_rejects_wrong_fists() -> None:
    """午餐蔬菜必须是 2 拳：写成 1 拳要指出具体餐位。"""
    slots = [
        _slot("蔬菜", "veg", 1),
        _slot("主食", "staple", 1),
        _slot("肉类", "protein", 1),
    ]
    ok, problems = meal_rules.validate_meal("lunch", slots)
    assert not ok
    assert any("第1餐位" in p for p in problems)


def test_validate_unknown_meal_type() -> None:
    ok, problems = meal_rules.validate_meal("supper", [])
    assert not ok and problems == ["未知餐次：supper"]


def test_pick_recipe_prefers_unused() -> None:
    """近 3 天用过的菜谱不再出现（轮换）。"""
    candidates = [
        {"id": 1, "tags": []},
        {"id": 2, "tags": []},
        {"id": 3, "tags": []},
    ]
    for _ in range(10):
        picked = meal_rules.pick_recipe(candidates, recent_3d=[1, 2], recent_1d=[],
                                        meal_type="dinner", weekday=0)
        assert picked == 3


def test_pick_recipe_relaxes_to_1d() -> None:
    """全部用过时放宽到近 1 天窗口（只排除昨天）。"""
    candidates = [{"id": 1, "tags": []}, {"id": 2, "tags": []}]
    for _ in range(10):
        picked = meal_rules.pick_recipe(candidates, recent_3d=[1, 2], recent_1d=[1],
                                        meal_type="dinner", weekday=0)
        assert picked == 2


def test_pick_recipe_workday_lunch_bento_only() -> None:
    """工作日午餐只在「带饭友好」里选；周末放全量。"""
    candidates = [
        {"id": 1, "tags": []},
        {"id": 2, "tags": ["带饭友好"]},
    ]
    for _ in range(10):
        assert meal_rules.pick_recipe(candidates, [], [], "lunch", weekday=0) == 2
        # 周六（weekday=5）两者皆可，但 1/2 均合法
        assert meal_rules.pick_recipe(candidates, [], [], "lunch", weekday=5) in (1, 2)


def test_pick_recipe_empty_pool() -> None:
    assert meal_rules.pick_recipe([], [], [], "dinner", weekday=0) is None
    # 工作日午餐无带饭友好候选 → None（调用方兜底提示）
    assert meal_rules.pick_recipe([{"id": 1, "tags": []}], [], [], "lunch", weekday=2) is None


def test_is_weekend() -> None:
    assert not meal_rules.is_weekend(0)   # 周一
    assert not meal_rules.is_weekend(4)   # 周五
    assert meal_rules.is_weekend(5)       # 周六
    assert meal_rules.is_weekend(6)       # 周日


def test_templates_satiety() -> None:
    assert meal_rules.SATIETY == {"lunch": "八分饱", "dinner": "六分饱"}
    assert set(meal_rules.MEAL_TEMPLATES) == {"breakfast", "lunch", "dinner"}


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all passed")
