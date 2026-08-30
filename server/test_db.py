"""db.py DAO 回归测试（临时库，不动真实数据）。

运行：.venv/bin/python -m server.test_db
（兼容 pytest：函数名 test_ 前缀 + 断言）

关键回归：删除带消息的会话不能因外键约束失败（PRAGMA foreign_keys = ON，
必须先删子表 messages 再删父表 conversations）。
"""

import tempfile
from pathlib import Path

from server import db


def _fresh_db() -> Path:
    """让 db 模块指向全新的临时库（须在首次 get_conn 之前替换 DB_PATH）。"""
    tmp = Path(tempfile.mkdtemp()) / "test.db"
    db._conn = None
    db.DB_PATH = tmp
    return tmp


def test_delete_conversation_with_messages() -> None:
    """带消息的会话删除：先删子表再删父表，外键不报错，两边都清干净。"""
    _fresh_db()
    conv = db.create_conversation("回归-带消息")
    cid = conv["id"]
    db.add_message(cid, "user", "帮我看下这个衣柜")

    assert db.delete_conversation(cid) is True
    assert db.get_conversation(cid) is None
    assert db.list_messages(cid) == []


def test_delete_missing_conversation() -> None:
    """不存在的会话：返回 False（上层转 404），不抛异常。"""
    _fresh_db()
    assert db.delete_conversation(99999) is False


def test_delete_empty_conversation() -> None:
    """空会话删除：正常路径。"""
    _fresh_db()
    conv = db.create_conversation("回归-空会话")
    assert db.delete_conversation(conv["id"]) is True


def test_create_plan_manual_no_score() -> None:
    """手动新建计划（无物品/照片）：danshari_score 存 NULL，不伪造评分。"""
    _fresh_db()
    plan = db.create_plan(
        room="玄关", summary="先建个计划", danshari_score=None,
        discard_count=0, donate_count=0, keep_count=0,
    )
    assert plan["danshari_score"] is None
    assert plan["photos"] == []
    assert plan["tasks"] == []
    # 无评分计划不污染平均分（AVG 忽略 NULL）
    _fresh_db()
    p1 = db.create_plan(room="a", summary="", danshari_score=80,
                        discard_count=0, donate_count=0, keep_count=0)
    db.update_plan_status(p1["id"], "active")
    db.create_plan(room="b", summary="", danshari_score=None,
                   discard_count=0, donate_count=0, keep_count=0)
    assert db.avg_danshari_score() == 80.0


def test_plan_keeps_batch_photo_association() -> None:
    """同一批照片生成一个计划，计划详情应返回完整照片集合。"""
    _fresh_db()
    conv = db.create_conversation("回归-批量照片")
    photos = [db.create_photo(f"photos/test/{name}.jpg") for name in ("one", "two", "three")]
    plan = db.create_plan(
        room="客厅", summary="批量照片计划", danshari_score=80,
        discard_count=1, donate_count=1, keep_count=1,
        conversation_id=conv["id"], photo_ids=[p["id"] for p in photos],
    )

    detail = db.get_plan(plan["id"])
    assert detail is not None
    assert [p["id"] for p in detail["photos"]] == [p["id"] for p in photos]
    assert [p["id"] for p in db.list_plans()] == [plan["id"]]


def test_add_plan_photos_attaches_and_dedupes() -> None:
    """点计划加图：INSERT OR IGNORE 去重，重复关联不重复计数，详情返回完整集合。"""
    _fresh_db()
    plan = db.create_plan(room="衣柜", summary="", danshari_score=80,
                          discard_count=0, donate_count=0, keep_count=0)
    p1, p2, p3 = (db.create_photo(f"photos/t/{i}.jpg")["id"] for i in range(3))
    assert db.add_plan_photos(plan["id"], [p1, p2]) == 2
    assert db.add_plan_photos(plan["id"], [p2, p3]) == 1  # p2 已关联，去重
    assert {ph["id"] for ph in db.get_plan(plan["id"])["photos"]} == {p1, p2, p3}


# ---------- 三餐：meal_plans 幂等 / 轮换窗口 / grocery ----------

def _seed_one_recipe() -> int:
    rows = db.seed_recipes([{
        "name": "测试菜", "meal_type": "dinner",
        "slots": [{"slot": "蔬菜", "kind": "veg", "fists": 2, "food": "菜心 400g"},
                  {"slot": "鱼虾贝", "kind": "seafood", "fists": 1, "food": "基围虾 300g"}],
        "ingredients": [{"name": "基围虾", "amount": "300g", "hima": "水产"}],
        "steps": ["Cook5 炒虾 3 分钟"], "cook_tool": "cook5", "cook_minutes": 25,
        "tags": ["Cook5"], "satiety_hint": "六分饱",
    }])
    assert rows == 1
    return db.list_recipes("dinner")[0]["id"]


def test_meal_plan_upsert_idempotent() -> None:
    """UNIQUE(plan_date, meal_type)：重复 ensure 不覆盖已有计划。"""
    _fresh_db()
    rid = _seed_one_recipe()
    first = db.upsert_meal_plan("2026-08-24", "dinner", rid, mode="cook")
    db.update_meal_status(first["id"], "eaten")
    again = db.upsert_meal_plan("2026-08-24", "dinner", rid)
    assert again["id"] == first["id"] and again["status"] == "eaten"
    assert len(db.get_day_meals("2026-08-24")) == 1


def test_recent_recipe_ids_window() -> None:
    """轮换窗口 [end-days, end)：只含近 N 天，不含 end 当天。"""
    _fresh_db()
    rid = _seed_one_recipe()
    db.upsert_meal_plan("2026-08-20", "dinner", rid)
    db.upsert_meal_plan("2026-08-24", "dinner", rid)
    assert db.recent_recipe_ids("dinner", "2026-08-23", days=3) == [rid]
    assert db.recent_recipe_ids("dinner", "2026-08-24", days=3) == []


def test_grocery_rows_lifecycle() -> None:
    """增删查 + 勾选/清空：reroll 删旧插新、采购完成清已勾选。"""
    _fresh_db()
    db.add_grocery_rows([
        {"plan_date": "2026-08-25", "meal_type": "dinner", "name": "基围虾",
         "amount": "300g", "hima": "水产"},
        {"plan_date": "2026-08-25", "meal_type": "breakfast", "name": "纯牛奶",
         "amount": "250ml", "hima": "肉蛋奶"},
    ])
    rows = db.list_grocery("2026-08-25", "2026-08-26")
    assert {r["name"] for r in rows} == {"基围虾", "纯牛奶"}  # 分组排序由服务层按固定分区序
    milk = next(r for r in rows if r["name"] == "纯牛奶")

    assert db.toggle_grocery(milk["id"], True) is True
    assert db.delete_grocery_for_meal("2026-08-25", "dinner") == 1  # reroll 删旧（晚餐基围虾）
    assert db.clear_checked_grocery() == 1                            # 已勾选的早餐牛奶被清
    assert db.list_grocery("2026-08-25", "2026-08-26") == []


# ---------- 时间轴账本：done_at / eaten_at / 区间计数 / timeline ----------

def _plan_with_task() -> int:
    plan = db.create_plan(room="时间轴", summary="", danshari_score=80,
                          discard_count=0, donate_count=0, keep_count=0)
    ids = db.create_tasks(plan["id"], [
        {"type": "organize", "title": "叠 T 恤", "steps": ["叠"], "est_minutes": 3}
    ])
    return ids[0]


def test_task_done_sets_done_at_once() -> None:
    """任务首次置 done 打 done_at；反复置 done 不覆盖；回退 done 后时间戳仍留痕。"""
    _fresh_db()
    tid = _plan_with_task()
    assert db.get_task(tid)["done_at"] is None
    db.update_task_status(tid, "done")
    t1 = db.get_task(tid)["done_at"]
    assert t1 is not None
    db.update_task_status(tid, "todo")
    db.update_task_status(tid, "done")
    assert db.get_task(tid)["done_at"] == t1  # 不覆盖首次完成时刻


def test_meal_eaten_sets_eaten_at() -> None:
    """餐首次置 eaten 打 eaten_at。"""
    _fresh_db()
    rid = _seed_one_recipe()
    plan = db.upsert_meal_plan("2026-08-24", "dinner", rid)
    assert db.get_meal_plan("2026-08-24", "dinner")["eaten_at"] is None
    db.update_meal_status(plan["id"], "eaten")
    assert db.get_meal_plan("2026-08-24", "dinner")["eaten_at"] is not None


def test_week_interval_counts() -> None:
    """半开区间 [start, end) 计数：done/eaten 落在区间内才计入。"""
    _fresh_db()
    rid = _seed_one_recipe()
    tid = _plan_with_task()
    db.update_task_status(tid, "done")
    plan = db.upsert_meal_plan("2026-08-24", "dinner", rid)
    db.update_meal_status(plan["id"], "eaten")
    # 今天一定落在 [今天-7, 明天) 内
    from datetime import date, timedelta
    today = date.today()
    start = (today - timedelta(days=7)).isoformat()
    end = (today + timedelta(days=1)).isoformat()
    assert db.count_done_tasks_between(start, end) == 1
    assert db.count_eaten_meals_between(start, end) == 1
    assert db.count_done_tasks_between("2000-01-01", "2000-01-02") == 0


def test_timeline_events_merges_home_and_body() -> None:
    """家的账（任务 done + 计划创建）+ 身体的账（餐 eaten）合成一条时间轴。"""
    _fresh_db()
    rid = _seed_one_recipe()
    tid = _plan_with_task()
    db.update_task_status(tid, "done")
    plan = db.upsert_meal_plan("2026-08-24", "dinner", rid)
    db.update_meal_status(plan["id"], "eaten")

    events = db.timeline_events(limit=50)
    kinds = {e["kind"] for e in events}
    icons = {e["icon"] for e in events}
    assert "home" in kinds and "body" in kinds
    assert "task" in icons and "meal" in icons and "plan" in icons
    assert any("叠 T 恤" in e["text"] for e in events)
    assert any("测试菜" in e["text"] for e in events)
    ts = [e["ts"] for e in events]
    assert ts == sorted(ts, reverse=True)  # 时间倒序


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all passed")
