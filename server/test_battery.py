"""battery.py 三格电引擎测试：电量真改内容供给 + 诚实记账。

运行：.venv/bin/python -m server.test_battery（pytest 兼容）

关键回归：
- 档位上限决定任务规模（半格绝不给出 15 分钟任务）
- 有真实待办任务先给真实任务，没有才给兜底建议（诚实，不伪造加分）
- 满格=可选菜单 / 半格=直接给晚餐 / 没电=歇着
- 努力轨迹只数真实完成（任务 done + 餐 eaten）
"""

import datetime as dt
import tempfile
from pathlib import Path

from server import battery, db, meals


def _fresh_db() -> Path:
    """让 db 模块指向全新的临时库（须在首次 get_conn 之前替换 DB_PATH）。"""
    tmp = Path(tempfile.mkdtemp()) / "test.db"
    db._conn = None
    db.DB_PATH = tmp
    return tmp


def _seed_recipes() -> None:
    """种一道晚餐 + 一道午餐（菜谱库为空时 ensure_day 会抛错，必须先种）。"""
    db.seed_recipes([
        {
            "name": "蒜蓉基围虾", "meal_type": "dinner",
            "slots": [{"slot": "鱼虾贝", "kind": "seafood", "fists": 1, "food": "基围虾 300g"}],
            "ingredients": [{"name": "基围虾", "amount": "300g", "hima": "水产"}],
            "steps": ["Cook5 炒虾 3 分钟"], "cook_tool": "cook5", "cook_minutes": 25,
            "tags": ["家常"], "satiety_hint": "六分饱",
        },
        {
            "name": "番茄牛腩面", "meal_type": "lunch",
            "slots": [{"slot": "主食", "kind": "staple", "fists": 1, "food": "面条 150g"}],
            "ingredients": [{"name": "番茄", "amount": "1 个", "hima": "蔬菜"}],
            "steps": ["煮面"], "cook_tool": "stove", "cook_minutes": 20,
            "tags": ["带饭友好"], "satiety_hint": "八分饱",
        },
        {
            "name": "鸡蛋牛奶", "meal_type": "breakfast",
            "slots": [{"slot": "蛋白质", "kind": "protein", "fists": 1, "food": "鸡蛋 1 个"}],
            "ingredients": [{"name": "牛奶", "amount": "250ml", "hima": "肉蛋奶"}],
            "steps": ["煮蛋"], "cook_tool": "none", "cook_minutes": 5,
            "tags": [], "satiety_hint": "八分饱",
        },
    ])


def _task(title: str, est_minutes: int, status: str = "todo") -> int:
    plan = db.create_plan(room="测试区", summary="", danshari_score=80,
                          discard_count=0, donate_count=0, keep_count=0)
    ids = db.create_tasks(plan["id"], [
        {"type": "organize", "title": title, "steps": ["做"], "est_minutes": est_minutes}
    ])
    if status != "todo":
        db.update_task_status(ids[0], status)
    return ids[0]


def test_task_scope_bounded_by_level() -> None:
    """档位上限硬约束：半格（5 分钟）绝不推荐 10 分钟任务。"""
    _fresh_db()
    _task("大任务", est_minutes=10)
    half = battery.recommend_task("half")
    assert half["source"] == "suggestion"          # 10 分钟任务超半格上限，不硬塞
    assert half["est_minutes"] <= 5
    full = battery.recommend_task("full")
    assert full["source"] == "task" and full["title"] == "大任务"


def test_recommend_picks_smallest_real_task() -> None:
    """满格有多个候选时，先给最短的（省力优先）。"""
    _fresh_db()
    _task("十五分钟事", est_minutes=15)
    _task("五分钟事", est_minutes=5)
    full = battery.recommend_task("full")
    assert full["source"] == "task" and full["title"] == "五分钟事"


def test_fallback_when_no_pending_task() -> None:
    """无待办任务：兜底建议，且不超过档位上限。"""
    _fresh_db()
    for level, max_min in (("full", 15), ("half", 5), ("empty", 2)):
        rec = battery.recommend_task(level)
        assert rec["source"] == "suggestion"
        assert rec["est_minutes"] <= max_min


def test_meal_supply_modes() -> None:
    """满格=可选菜单 / 半格=直接给晚餐 / 没电=别勉强。"""
    _fresh_db()
    _seed_recipes()
    full = battery.meal_supply("full")
    assert full["give"] is False and full["meals"]            # 可选菜单
    assert any(m["name"] for m in full["meals"])
    half = battery.meal_supply("half")
    assert half["give"] is True and half["meal"] and half["meal"]["name"]  # 直接给晚餐
    empty = battery.meal_supply("empty")
    assert empty["give"] is False and empty["meal"] is None    # 别勉强


def test_trajectory_counts_only_real_completions() -> None:
    """努力轨迹只数真实完成：任务 done + 餐 eaten；today 必然落在本周区间。"""
    _fresh_db()
    _seed_recipes()
    today = dt.date.today().isoformat()
    before = battery.trajectory()
    assert before["this_week"] == 0
    # 完成一个任务 + 吃掉一餐
    _task("一件小事", est_minutes=5)
    db.update_task_status(_task("第二件", est_minutes=3), "done")
    meals.ensure_day(today)
    dinner = db.get_day_meals(today).get("dinner")
    db.update_meal_status(dinner["id"], "eaten")
    after = battery.trajectory()
    assert after["this_week"] == 2  # 1 个 done 任务 + 1 餐 eaten


def test_home_payload_structure() -> None:
    """/api/home 负载：档位 + 任务 + 餐 + 鼓励 + 轨迹，rest 只在没电档开放。"""
    _fresh_db()
    _seed_recipes()
    half = battery.home_payload("half")
    assert half["energy"] == "half"
    assert half["level"]["max_min"] == 5
    assert half["task"]["est_minutes"] <= 5
    assert half["rest_allowed"] is False
    assert half["encouragement"] and half["trajectory"]["line"]
    empty = battery.home_payload("empty")
    assert empty["rest_allowed"] is True


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all passed")
