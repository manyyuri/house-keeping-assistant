"""SQLite 初始化 + DAO（sqlite3 标准库，纯函数式，无 ORM）。

数据库文件 server/data/app.db，启动时自动建表（CREATE TABLE IF NOT EXISTS）。
FastAPI 同步端点在线程池执行，这里用模块级连接 + 写锁保证线程安全。
"""

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from server import rules  # normalize_name：物品稳定身份匹配（无环：rules 惰性 import db）

DATA_DIR = Path(__file__).resolve().parent / "data"
PHOTOS_DIR_NAME = "photos"  # DATA_DIR 下的照片根目录，DB 存相对路径 photos/...
DB_PATH = DATA_DIR / "app.db"

_conn: Optional[sqlite3.Connection] = None
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT DEFAULT '新整理对话',
  room TEXT,
  created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id INTEGER NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  attachments TEXT,
  created_at TEXT DEFAULT (datetime('now','localtime')),
  FOREIGN KEY(conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS photos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT NOT NULL,
  room TEXT,
  vision_text TEXT,
  created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  photo_id INTEGER,
  name TEXT NOT NULL,
  category TEXT,
  quantity INTEGER DEFAULT 1,
  keep_status TEXT DEFAULT 'unjudged',
  reason TEXT,
  last_used TEXT,
  quarantine_until TEXT,
  created_at TEXT DEFAULT (datetime('now','localtime')),
  FOREIGN KEY(photo_id) REFERENCES photos(id)
);

CREATE TABLE IF NOT EXISTS plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id INTEGER,
  room TEXT NOT NULL,
  summary TEXT,
  danshari_score INTEGER,
  discard_count INTEGER DEFAULT 0,
  donate_count INTEGER DEFAULT 0,
  keep_count INTEGER DEFAULT 0,
  status TEXT DEFAULT 'active',
  created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS plan_photos (
  plan_id INTEGER NOT NULL,
  photo_id INTEGER NOT NULL,
  PRIMARY KEY (plan_id, photo_id),
  FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE,
  FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id INTEGER NOT NULL,
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  steps TEXT,
  est_minutes INTEGER,
  due_date TEXT,
  status TEXT DEFAULT 'todo',
  done_at TEXT,                      -- 完成时刻（时间轴账本用，诚实记账）
  created_at TEXT DEFAULT (datetime('now','localtime')),
  FOREIGN KEY(plan_id) REFERENCES plans(id)
);

CREATE TABLE IF NOT EXISTS recipes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  meal_type TEXT NOT NULL,          -- breakfast/lunch/dinner
  slots TEXT NOT NULL,              -- JSON 餐位：[{slot,kind,fists,food}]
  ingredients TEXT NOT NULL,        -- JSON 食材：[{name,amount,hima}]
  steps TEXT,                       -- JSON 步骤（Cook5 步骤显式写「Cook5」）
  cook_tool TEXT DEFAULT 'none',    -- cook5 | stove | none
  cook_minutes INTEGER,
  tags TEXT,                        -- JSON 标签：["带饭友好",…]
  cuisine TEXT,                     -- 菜系：川菜/粤菜/韩餐/日料/泰式/家常
  satiety_hint TEXT                 -- 八分饱/六分饱，展示用
);

CREATE TABLE IF NOT EXISTS meal_plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_date TEXT NOT NULL,          -- yyyy-mm-dd
  meal_type TEXT NOT NULL,          -- breakfast/lunch/dinner
  recipe_id INTEGER,
  mode TEXT DEFAULT 'cook',         -- cook(现做) | bento(带饭，前一晚制)
  status TEXT DEFAULT 'planned',    -- planned/eaten/skipped
  eaten_at TEXT,                    -- 吃掉的时刻（时间轴账本用，诚实记账）
  note TEXT,
  created_at TEXT DEFAULT (datetime('now','localtime')),
  UNIQUE(plan_date, meal_type),
  FOREIGN KEY(recipe_id) REFERENCES recipes(id)
);

CREATE TABLE IF NOT EXISTS grocery_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_date TEXT NOT NULL,
  meal_type TEXT NOT NULL,
  name TEXT NOT NULL,
  amount TEXT,
  hima_category TEXT,               -- 盒马分区：蔬菜/水产/肉蛋奶/主食粮油/调味
  checked INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now','localtime'))
);
"""


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """老库迁移：表缺列则 ALTER TABLE ADD COLUMN（CREATE TABLE IF NOT EXISTS 不会补列）。"""
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        with _lock:
            conn.executescript(SCHEMA)
            # 老库迁移：时间轴账本列（tasks.done_at / meal_plans.eaten_at）
            _ensure_column(conn, "tasks", "done_at", "done_at TEXT")
            _ensure_column(conn, "meal_plans", "eaten_at", "eaten_at TEXT")
            conn.commit()
        _conn = conn
    return _conn


def _rows_to_dicts(rows: Iterable[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [dict(r) for r in rows]


# ---------- conversations ----------

def create_conversation(title: str = "新整理对话", room: Optional[str] = None) -> Dict[str, Any]:
    conn = get_conn()
    with _lock:
        cur = conn.execute(
            "INSERT INTO conversations(title, room) VALUES(?, ?)", (title, room)
        )
        conn.commit()
    return get_conversation(cur.lastrowid)


def get_conversation(conversation_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
    ).fetchone()
    return dict(row) if row else None


def list_conversations() -> List[Dict[str, Any]]:
    conn = get_conn()
    return _rows_to_dicts(
        conn.execute("SELECT * FROM conversations ORDER BY id DESC").fetchall()
    )


def delete_conversation(conversation_id: int) -> bool:
    """删除会话及其消息（照片/物品/计划独立于会话存在，不级联）。

    注意删除顺序：messages 有指向 conversations 的外键且
    PRAGMA foreign_keys = ON，必须先删子表再删父表，否则
    sqlite3.IntegrityError → 接口 500。
    """
    conn = get_conn()
    with _lock:
        conn.execute(
            "DELETE FROM messages WHERE conversation_id = ?", (conversation_id,)
        )
        cur = conn.execute(
            "DELETE FROM conversations WHERE id = ?", (conversation_id,)
        )
        conn.commit()
    return cur.rowcount > 0


# ---------- messages ----------

def add_message(
    conversation_id: int,
    role: str,
    content: str,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    conn = get_conn()
    att_json = json.dumps(attachments, ensure_ascii=False) if attachments else None
    with _lock:
        cur = conn.execute(
            "INSERT INTO messages(conversation_id, role, content, attachments)"
            " VALUES(?,?,?,?)",
            (conversation_id, role, content, att_json),
        )
        conn.commit()
    row = conn.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)).fetchone()
    d = dict(row)
    d["attachments"] = json.loads(d["attachments"]) if d["attachments"] else []
    return d


def list_messages(conversation_id: int) -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,)
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["attachments"] = json.loads(d["attachments"]) if d["attachments"] else []
        out.append(d)
    return out


# ---------- photos ----------

def create_photo(path: str, room: Optional[str] = None) -> Dict[str, Any]:
    conn = get_conn()
    with _lock:
        cur = conn.execute("INSERT INTO photos(path, room) VALUES(?,?)", (path, room))
        conn.commit()
    return get_photo(cur.lastrowid)


def get_photo(photo_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
    return dict(row) if row else None


def update_photo_vision(photo_id: int, room: Optional[str], vision_text: str) -> None:
    conn = get_conn()
    with _lock:
        conn.execute(
            "UPDATE photos SET room = ?, vision_text = ? WHERE id = ?",
            (room, vision_text, photo_id),
        )
        conn.commit()


def get_photos(photo_ids: List[int]) -> List[Dict[str, Any]]:
    conn = get_conn()
    if not photo_ids:
        return []
    marks = ",".join("?" * len(photo_ids))
    rows = conn.execute(
        f"SELECT * FROM photos WHERE id IN ({marks})", photo_ids
    ).fetchall()
    by_id = {r["id"]: dict(r) for r in rows}
    return [by_id[i] for i in photo_ids if i in by_id]


# ---------- items ----------

def save_items(
    photo_id: Optional[int], items: List[Dict[str, Any]]
) -> Dict[str, int]:
    """批量入库，keep_status 默认 unjudged。

    稳定身份：同一张照片内按归一化名去重合并（同名累加 quantity，不重复插行），
    避免同一件物品被反复拍照/重复识别堆成多行，稀释统计与观察期可信度。

    返回 {"saved": 请求总件数(按 quantity 合计), "deduped": 被合并件数}。
    """
    conn = get_conn()
    existing: Dict[str, List[int]] = {}  # norm -> [id, quantity]
    with _lock:
        if photo_id is not None:
            for r in conn.execute(
                "SELECT id, name, quantity FROM items WHERE photo_id = ?", (photo_id,)
            ).fetchall():
                existing[rules.normalize_name(r["name"])] = [r["id"], r["quantity"]]
        total = 0
        deduped = 0
        for it in items:
            name = str(it.get("name") or "未命名物品")
            qty = max(1, int(it.get("quantity") or 1))
            total += qty
            norm = rules.normalize_name(name)
            if norm in existing:
                eid, eq = existing[norm]
                conn.execute("UPDATE items SET quantity = ? WHERE id = ?", (eq + qty, eid))
                existing[norm][1] = eq + qty
                deduped += qty
            else:
                cur = conn.execute(
                    "INSERT INTO items(photo_id, name, category, quantity, keep_status)"
                    " VALUES(?,?,?,?, 'unjudged')",
                    (photo_id, name, it.get("category") or "other", qty),
                )
                existing[norm] = [cur.lastrowid, qty]
        conn.commit()
    return {"saved": total, "deduped": deduped}


def query_items(
    keep_status: Optional[str] = None,
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    photo_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    conn = get_conn()
    sql = "SELECT * FROM items WHERE 1=1"
    args: List[Any] = []
    if keep_status:
        sql += " AND keep_status = ?"
        args.append(keep_status)
    if category:
        sql += " AND category = ?"
        args.append(category)
    if photo_id is not None:
        sql += " AND photo_id = ?"
        args.append(photo_id)
    if keyword:
        sql += " AND name LIKE ?"
        args.append(f"%{keyword}%")
    sql += " ORDER BY id DESC"
    return _rows_to_dicts(conn.execute(sql, args).fetchall())


def get_item(item_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def update_item(
    item_id: int,
    keep_status: Optional[str] = None,
    last_used: Optional[str] = None,
    reason: Optional[str] = None,
    quarantine_until: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    sets, args = [], []
    if keep_status is not None:
        sets.append("keep_status = ?")
        args.append(keep_status)
    if last_used is not None:
        sets.append("last_used = ?")
        args.append(last_used)
    if reason is not None:
        sets.append("reason = ?")
        args.append(reason)
    if quarantine_until is not None:
        sets.append("quarantine_until = ?")
        args.append(quarantine_until)
    if not sets:
        return get_item(item_id)
    with _lock:
        conn.execute(
            f"UPDATE items SET {', '.join(sets)} WHERE id = ?", (*args, item_id)
        )
        conn.commit()
    return get_item(item_id)


def count_items(keep_status: str) -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT COALESCE(SUM(quantity),0) AS n FROM items WHERE keep_status = ?",
        (keep_status,),
    ).fetchone()
    return int(row["n"])


def active_hesitate_items() -> List[Dict[str, Any]]:
    """观察期未到期的犹豫物品（quarantine_until > 今天）。"""
    conn = get_conn()
    return _rows_to_dicts(
        conn.execute(
            "SELECT * FROM items WHERE keep_status = 'hesitate'"
            " AND quarantine_until > date('now','localtime') ORDER BY quarantine_until"
        ).fetchall()
    )


def expired_quarantine_items() -> List[Dict[str, Any]]:
    """观察期已到期的犹豫物品（quarantine_until <= 今天）。"""
    conn = get_conn()
    return _rows_to_dicts(
        conn.execute(
            "SELECT * FROM items WHERE keep_status = 'hesitate'"
            " AND quarantine_until <= date('now','localtime') ORDER BY quarantine_until"
        ).fetchall()
    )


# ---------- plans ----------

def create_plan(
    room: str,
    summary: str,
    danshari_score: Optional[int],
    discard_count: int,
    donate_count: int,
    keep_count: int,
    conversation_id: Optional[int] = None,
    photo_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    conn = get_conn()
    with _lock:
        cur = conn.execute(
            "INSERT INTO plans(conversation_id, room, summary, danshari_score,"
            " discard_count, donate_count, keep_count)"
            " VALUES(?,?,?,?,?,?,?)",
            (conversation_id, room, summary, danshari_score,
             discard_count, donate_count, keep_count),
        )
        plan_id = cur.lastrowid
        for photo_id in photo_ids or []:
            conn.execute(
                "INSERT OR IGNORE INTO plan_photos(plan_id, photo_id) VALUES(?, ?)",
                (plan_id, photo_id),
            )
        conn.commit()
    return get_plan(plan_id)


def add_plan_photos(plan_id: int, photo_ids: List[int]) -> int:
    """把照片关联到已有计划（INSERT OR IGNORE 去重）。返回新增关联数。

    供「点计划→加图」接口：上传走 /api/upload，关联走这里。
    """
    conn = get_conn()
    added = 0
    with _lock:
        for photo_id in photo_ids:
            cur = conn.execute(
                "INSERT OR IGNORE INTO plan_photos(plan_id, photo_id) VALUES(?, ?)",
                (plan_id, photo_id),
            )
            added += cur.rowcount
        conn.commit()
    return added


def _plan_photos(plan_id: int) -> List[Dict[str, Any]]:
    conn = get_conn()
    return _rows_to_dicts(conn.execute(
        "SELECT p.* FROM photos p JOIN plan_photos pp ON pp.photo_id = p.id "
        "WHERE pp.plan_id = ? ORDER BY p.id",
        (plan_id,),
    ).fetchall())


def _plan_hesitate_count(plan_id: int) -> int:
    """计划关联照片下处于 90 天观察期的物品数（hesitate_count）。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM items"
        " WHERE keep_status = 'hesitate' AND photo_id IN"
        " (SELECT photo_id FROM plan_photos WHERE plan_id = ?)",
        (plan_id,),
    ).fetchone()
    return int(row["n"])


def _plan_items(plan_id: int) -> List[Dict[str, Any]]:
    """计划关联照片下的全部物品（判定色带/物品名展示用）。"""
    conn = get_conn()
    return _rows_to_dicts(conn.execute(
        "SELECT i.* FROM items i JOIN plan_photos pp ON pp.photo_id = i.photo_id"
        " WHERE pp.plan_id = ? ORDER BY i.id",
        (plan_id,),
    ).fetchall())


def get_plan(plan_id: int, with_items: bool = True) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["tasks"] = list_tasks(plan_id=plan_id)
    d["photos"] = _plan_photos(plan_id)
    d["hesitate_count"] = _plan_hesitate_count(plan_id)
    d["items"] = _plan_items(plan_id) if with_items else []
    return d


def list_plans(status: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM plans WHERE status = ? ORDER BY id DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM plans ORDER BY id DESC").fetchall()
    return [get_plan(row["id"], with_items=False) for row in rows]


def update_plan_status(plan_id: int, status: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    with _lock:
        conn.execute("UPDATE plans SET status = ? WHERE id = ?", (status, plan_id))
        conn.commit()
    return get_plan(plan_id)


def update_plan_content(
    plan_id: int,
    room: str,
    summary: str,
    danshari_score: Optional[int],
    discard_count: int,
    donate_count: int,
    keep_count: int,
) -> Optional[Dict[str, Any]]:
    """覆写计划内容（重新生成用）：区域/总结/评分/计数就地更新，不新建。

    保留 conversation 归属与计划状态；照片关联不动（输入照片已在 plan_photos 中）。
    """
    conn = get_conn()
    with _lock:
        conn.execute(
            "UPDATE plans SET room = ?, summary = ?, danshari_score = ?,"
            " discard_count = ?, donate_count = ?, keep_count = ? WHERE id = ?",
            (room, summary, danshari_score, discard_count, donate_count, keep_count, plan_id),
        )
        conn.commit()
    return get_plan(plan_id)


def delete_plan_photo_items(plan_id: int) -> None:
    """删除计划关联照片下的物品（重新生成前清场）。

    否则同一张照片再次识别 → save_items 按归一化名累加 quantity，数量会被翻倍。
    """
    conn = get_conn()
    with _lock:
        conn.execute(
            "DELETE FROM items WHERE photo_id IN"
            " (SELECT photo_id FROM plan_photos WHERE plan_id = ?)",
            (plan_id,),
        )
        conn.commit()


def delete_plan_pending_tasks(plan_id: int) -> None:
    """删除计划未完成任务（重新生成前清场）。

    仅删 done_at IS NULL 的行：已完成任务进过时间轴账本（诚实记账），必须保留。
    """
    conn = get_conn()
    with _lock:
        conn.execute(
            "DELETE FROM tasks WHERE plan_id = ? AND done_at IS NULL", (plan_id,)
        )
        conn.commit()


def avg_danshari_score() -> Optional[float]:
    """活跃/已完成计划的平均断舍离评分。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT AVG(danshari_score) AS s FROM plans"
        " WHERE status IN ('active','completed')"
    ).fetchone()
    return round(float(row["s"]), 1) if row["s"] is not None else None


# ---------- tasks ----------

def create_tasks(
    plan_id: int, tasks: List[Dict[str, Any]]
) -> List[int]:
    conn = get_conn()
    ids = []
    with _lock:
        for t in tasks:
            steps_json = json.dumps(t.get("steps") or [], ensure_ascii=False)
            cur = conn.execute(
                "INSERT INTO tasks(plan_id, type, title, steps, est_minutes, due_date)"
                " VALUES(?,?,?,?,?,?)",
                (
                    plan_id,
                    t.get("type", "other"),
                    t.get("title", "未命名任务"),
                    steps_json,
                    int(t["est_minutes"]) if t.get("est_minutes") else None,
                    t.get("due_date"),
                ),
            )
            ids.append(cur.lastrowid)
        conn.commit()
    return ids


def list_tasks(
    status: Optional[str] = None,
    type_: Optional[str] = None,
    plan_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    conn = get_conn()
    sql = (
        "SELECT t.*, p.room AS plan_room FROM tasks t"
        " LEFT JOIN plans p ON t.plan_id = p.id WHERE 1=1"
    )
    args: List[Any] = []
    if status:
        sql += " AND t.status = ?"
        args.append(status)
    if type_:
        sql += " AND t.type = ?"
        args.append(type_)
    if plan_id is not None:
        sql += " AND t.plan_id = ?"
        args.append(plan_id)
    sql += " ORDER BY t.id DESC"
    out = []
    for r in conn.execute(sql, args).fetchall():
        d = dict(r)
        d["steps"] = json.loads(d["steps"]) if d["steps"] else []
        out.append(d)
    return out


def get_task(task_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["steps"] = json.loads(d["steps"]) if d["steps"] else []
    return d


def update_task_status(task_id: int, status: str) -> Optional[Dict[str, Any]]:
    """任务状态流转；首次置 done 时打 done_at（时间轴账本，诚实记账）。"""
    conn = get_conn()
    with _lock:
        cur = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if cur is None:
            conn.commit()
            return None
        if cur["status"] != "done" and status == "done":
            conn.execute(
                "UPDATE tasks SET status = ?, done_at = datetime('now','localtime') WHERE id = ?",
                (status, task_id),
            )
        else:
            conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
        conn.commit()
    return get_task(task_id)


def count_done_tasks() -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM tasks WHERE status = 'done'"
    ).fetchone()
    return int(row["n"])


def count_done_tasks_between(start: str, end: str) -> int:
    """[start, end) 半开区间内完成的任务数（done_at 落在区间）。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM tasks WHERE done_at IS NOT NULL"
        " AND date(done_at) >= ? AND date(done_at) < ?",
        (start, end),
    ).fetchone()
    return int(row["n"])


# ---------- recipes ----------

def _recipe_row(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    for k in ("slots", "ingredients", "steps", "tags"):
        d[k] = json.loads(d[k]) if d[k] else []
    return d


def list_recipes(meal_type: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_conn()
    if meal_type:
        rows = conn.execute(
            "SELECT * FROM recipes WHERE meal_type = ? ORDER BY id", (meal_type,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM recipes ORDER BY id").fetchall()
    return [_recipe_row(r) for r in rows]


def get_recipe(recipe_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    return _recipe_row(row) if row else None


def seed_recipes(rows: List[Dict[str, Any]]) -> int:
    """导入种子菜谱（调用方先确认表为空）。返回导入条数。"""
    conn = get_conn()
    with _lock:
        for r in rows:
            conn.execute(
                "INSERT INTO recipes(name, meal_type, slots, ingredients, steps,"
                " cook_tool, cook_minutes, tags, cuisine, satiety_hint)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    r["name"], r["meal_type"],
                    json.dumps(r["slots"], ensure_ascii=False),
                    json.dumps(r["ingredients"], ensure_ascii=False),
                    json.dumps(r.get("steps") or [], ensure_ascii=False),
                    r.get("cook_tool") or "none",
                    r.get("cook_minutes"),
                    json.dumps(r.get("tags") or [], ensure_ascii=False),
                    r.get("cuisine") or "家常",
                    r.get("satiety_hint"),
                ),
            )
        conn.commit()
    return len(rows)


# 菜谱改名映射（seed 维护菜名/菜的内容时，旧库按旧名定位后整体刷新，保 id）
RECIPE_RENAMES: Dict[str, str] = {
    "荷兰豆牛柳杂粮饭（便当）": "芥蓝牛柳杂粮饭（便当）",
    "芥蓝牛柳杂粮饭（便当）": "芦笋牛柳杂粮饭（便当）",
    "白灼虾 + 清炒荷兰豆": "白灼虾 + 清炒芦笋",
    "椒盐虾 + 白灼芥蓝": "椒盐虾 + 白灼西兰花",
}


def _ensure_column(conn: sqlite3.Connection, table: str, col: str, ddl: str) -> None:
    cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def sync_seed_recipes(rows: List[Dict[str, Any]]) -> int:
    """把最新 seed 菜谱库同步进非空 recipes 表（保留 id，meal_plans FK 不断）。

    - 补 cuisine 列（老库升级）
    - 已存在：菜系不同则更新 cuisine；若是「改名菜」则整行刷新到新内容
    - 新菜：INSERT
    返回新增条数。幂等，可重复执行。
    """
    conn = get_conn()
    added = 0
    with _lock:
        _ensure_column(conn, "recipes", "cuisine", "TEXT")
        existing = {
            r["name"]: dict(r) for r in conn.execute("SELECT * FROM recipes")
        }
        # 旧名 → 对应行，供改名菜按新名反查旧 id
        by_name = dict(existing)
        for old, new in RECIPE_RENAMES.items():
            if old in existing and new not in by_name:
                by_name[new] = existing[old]
        renamed_new = set(RECIPE_RENAMES.values())
        for r in rows:
            name = r["name"]
            row = by_name.get(name)
            if row is None:
                conn.execute(
                    "INSERT INTO recipes(name, meal_type, slots, ingredients, steps,"
                    " cook_tool, cook_minutes, tags, cuisine, satiety_hint)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        name, r["meal_type"],
                        json.dumps(r["slots"], ensure_ascii=False),
                        json.dumps(r["ingredients"], ensure_ascii=False),
                        json.dumps(r.get("steps") or [], ensure_ascii=False),
                        r.get("cook_tool") or "none",
                        r.get("cook_minutes"),
                        json.dumps(r.get("tags") or [], ensure_ascii=False),
                        r.get("cuisine") or "家常",
                        r.get("satiety_hint"),
                    ),
                )
                added += 1
                continue
            rid = row["id"]
            if name in renamed_new or row.get("cuisine") != (r.get("cuisine") or "家常"):
                if name in renamed_new:
                    # 整行刷新（改名菜内容可能整体变了）
                    conn.execute(
                        "UPDATE recipes SET name=?, meal_type=?, slots=?, ingredients=?,"
                        " steps=?, cook_tool=?, cook_minutes=?, tags=?, cuisine=?, satiety_hint=?"
                        " WHERE id=?",
                        (
                            name, r["meal_type"],
                            json.dumps(r["slots"], ensure_ascii=False),
                            json.dumps(r["ingredients"], ensure_ascii=False),
                            json.dumps(r.get("steps") or [], ensure_ascii=False),
                            r.get("cook_tool") or "none",
                            r.get("cook_minutes"),
                            json.dumps(r.get("tags") or [], ensure_ascii=False),
                            r.get("cuisine") or "家常",
                            r.get("satiety_hint"),
                            rid,
                        ),
                    )
                else:
                    conn.execute(
                        "UPDATE recipes SET cuisine=? WHERE id=?",
                        (r.get("cuisine") or "家常", rid),
                    )
        # 清理：已从 seed 移除、且无任何餐计划引用的旧菜（保历史，绝不删被引用行）
        seed_names = {r["name"] for r in rows}
        conn.execute(
            "DELETE FROM recipes WHERE name NOT IN ("
            + ",".join("?" * len(seed_names))
            + ") AND id NOT IN (SELECT recipe_id FROM meal_plans WHERE recipe_id IS NOT NULL)",
            tuple(seed_names),
        )
        conn.commit()
    return added


# ---------- meal_plans ----------

def upsert_meal_plan(
    plan_date: str, meal_type: str, recipe_id: Optional[int], mode: str = "cook"
) -> Optional[Dict[str, Any]]:
    """幂等写入：当日该餐已有计划则原样返回（不覆盖换菜/打卡结果）。"""
    conn = get_conn()
    with _lock:
        conn.execute(
            "INSERT INTO meal_plans(plan_date, meal_type, recipe_id, mode)"
            " VALUES(?,?,?,?) ON CONFLICT(plan_date, meal_type) DO NOTHING",
            (plan_date, meal_type, recipe_id, mode),
        )
        conn.commit()
    return get_meal_plan(plan_date, meal_type)


def get_meal_plan(plan_date: str, meal_type: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM meal_plans WHERE plan_date = ? AND meal_type = ?",
        (plan_date, meal_type),
    ).fetchone()
    return dict(row) if row else None


def get_day_meals(plan_date: str) -> Dict[str, Dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM meal_plans WHERE plan_date = ?", (plan_date,)
    ).fetchall()
    return {r["meal_type"]: dict(r) for r in rows}


def replace_meal_recipe(plan_date: str, meal_type: str, recipe_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    with _lock:
        conn.execute(
            "UPDATE meal_plans SET recipe_id = ? WHERE plan_date = ? AND meal_type = ?",
            (recipe_id, plan_date, meal_type),
        )
        conn.commit()
    return get_meal_plan(plan_date, meal_type)


def list_meal_plans(start: str, end: str) -> List[Dict[str, Any]]:
    """日期闭区间内的计划（附菜名，供周视图）。"""
    conn = get_conn()
    return _rows_to_dicts(
        conn.execute(
            "SELECT p.*, r.name AS recipe_name, r.cook_minutes, r.cook_tool, r.tags"
            " FROM meal_plans p LEFT JOIN recipes r ON p.recipe_id = r.id"
            " WHERE p.plan_date >= ? AND p.plan_date <= ? ORDER BY p.plan_date, p.meal_type",
            (start, end),
        ).fetchall()
    )


def update_meal_status(meal_plan_id: int, status: str) -> Optional[Dict[str, Any]]:
    """餐状态流转；首次置 eaten 时打 eaten_at（时间轴账本，诚实记账）。"""
    conn = get_conn()
    with _lock:
        cur = conn.execute(
            "SELECT status FROM meal_plans WHERE id = ?", (meal_plan_id,)
        ).fetchone()
        if cur is None:
            conn.commit()
            return None
        if cur["status"] != "eaten" and status == "eaten":
            conn.execute(
                "UPDATE meal_plans SET status = ?, eaten_at = datetime('now','localtime')"
                " WHERE id = ?",
                (status, meal_plan_id),
            )
        else:
            conn.execute(
                "UPDATE meal_plans SET status = ? WHERE id = ?", (status, meal_plan_id)
            )
        conn.commit()
    row = conn.execute("SELECT * FROM meal_plans WHERE id = ?", (meal_plan_id,)).fetchone()
    return dict(row) if row else None


def count_eaten_meals_between(start: str, end: str) -> int:
    """[start, end) 半开区间内吃掉的餐数（eaten_at 落在区间）。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM meal_plans WHERE eaten_at IS NOT NULL"
        " AND date(eaten_at) >= ? AND date(eaten_at) < ?",
        (start, end),
    ).fetchone()
    return int(row["n"])


def timeline_events(limit: int = 50) -> List[Dict[str, Any]]:
    """时间轴账本：家的账（任务完成/计划创建）+ 身体的账（吃掉的餐）合成一条轴。

    只收录诚实可追溯的事件：任务 done_at、餐 eaten_at、计划 created_at 都有时间戳，
    按时间倒序返回。物品判定的时间戳暂未记录，不伪造进账本。
    """
    conn = get_conn()
    events: List[Dict[str, Any]] = []
    meal_label = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}
    for r in conn.execute(
        "SELECT title, done_at AS ts FROM tasks WHERE done_at IS NOT NULL"
        " ORDER BY done_at DESC LIMIT ?",
        (limit,),
    ).fetchall():
        events.append({"ts": r["ts"], "kind": "home", "icon": "task", "text": f"完成「{r['title']}」"})
    for r in conn.execute(
        "SELECT p.meal_type, p.eaten_at AS ts, r.name AS recipe FROM meal_plans p"
        " LEFT JOIN recipes r ON p.recipe_id = r.id WHERE p.eaten_at IS NOT NULL"
        " ORDER BY p.eaten_at DESC LIMIT ?",
        (limit,),
    ).fetchall():
        label = meal_label.get(r["meal_type"], r["meal_type"])
        name = r["recipe"] or "一餐"
        events.append({"ts": r["ts"], "kind": "body", "icon": "meal", "text": f"吃了{label}「{name}」"})
    for r in conn.execute(
        "SELECT room, created_at AS ts FROM plans ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall():
        events.append({"ts": r["ts"], "kind": "home", "icon": "plan", "text": f"整理了「{r['room']}」"})
    events.sort(key=lambda e: e["ts"] or "", reverse=True)
    return events[:limit]


def update_meal_note(meal_plan_id: int, note: str) -> None:
    conn = get_conn()
    with _lock:
        conn.execute("UPDATE meal_plans SET note = ? WHERE id = ?", (note, meal_plan_id))
        conn.commit()


def recent_recipe_ids(meal_type: str, end_date: str, days: int) -> List[int]:
    """[end_date - days, end_date) 窗口内该餐用过的菜谱 id（轮换去重用）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT recipe_id FROM meal_plans"
        " WHERE meal_type = ? AND recipe_id IS NOT NULL"
        " AND plan_date >= date(?, ?) AND plan_date < ?",
        (meal_type, end_date, f"-{days} day", end_date),
    ).fetchall()
    return [r["recipe_id"] for r in rows]


# ---------- grocery_items ----------

def add_grocery_rows(rows: List[Dict[str, Any]]) -> int:
    conn = get_conn()
    with _lock:
        for g in rows:
            conn.execute(
                "INSERT INTO grocery_items(plan_date, meal_type, name, amount, hima_category)"
                " VALUES(?,?,?,?,?)",
                (g["plan_date"], g["meal_type"], g["name"], g.get("amount"), g.get("hima")),
            )
        conn.commit()
    return len(rows)


def delete_grocery_for_meal(plan_date: str, meal_type: str) -> int:
    conn = get_conn()
    with _lock:
        cur = conn.execute(
            "DELETE FROM grocery_items WHERE plan_date = ? AND meal_type = ?",
            (plan_date, meal_type),
        )
        conn.commit()
    return cur.rowcount


def list_grocery(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    conn = get_conn()
    return _rows_to_dicts(
        conn.execute(
            "SELECT * FROM grocery_items WHERE plan_date >= ? AND plan_date <= ?"
            " ORDER BY hima_category, name, plan_date",
            (start_date, end_date),
        ).fetchall()
    )


def toggle_grocery(item_id: int, checked: bool) -> bool:
    conn = get_conn()
    with _lock:
        cur = conn.execute(
            "UPDATE grocery_items SET checked = ? WHERE id = ?",
            (1 if checked else 0, item_id),
        )
        conn.commit()
    return cur.rowcount > 0


def clear_checked_grocery() -> int:
    """删除全部已勾选行（采购完成）。"""
    conn = get_conn()
    with _lock:
        cur = conn.execute("DELETE FROM grocery_items WHERE checked = 1")
        conn.commit()
    return cur.rowcount
