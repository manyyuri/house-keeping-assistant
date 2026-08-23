"""SQLite 初始化 + DAO（sqlite3 标准库，纯函数式，无 ORM）。

数据库文件 server/data/app.db，启动时自动建表（CREATE TABLE IF NOT EXISTS）。
FastAPI 同步端点在线程池执行，这里用模块级连接 + 写锁保证线程安全。
"""

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

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

CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id INTEGER NOT NULL,
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  steps TEXT,
  est_minutes INTEGER,
  due_date TEXT,
  status TEXT DEFAULT 'todo',
  created_at TEXT DEFAULT (datetime('now','localtime')),
  FOREIGN KEY(plan_id) REFERENCES plans(id)
);
"""


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        with _lock:
            conn.executescript(SCHEMA)
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
) -> int:
    """批量入库，keep_status 默认 unjudged。返回入库件数（按 quantity 合计）。"""
    conn = get_conn()
    with _lock:
        for it in items:
            conn.execute(
                "INSERT INTO items(photo_id, name, category, quantity, keep_status)"
                " VALUES(?,?,?,?, 'unjudged')",
                (
                    photo_id,
                    it.get("name", "未命名物品"),
                    it.get("category") or "other",
                    int(it.get("quantity") or 1),
                ),
            )
        conn.commit()
    return sum(int(it.get("quantity") or 1) for it in items)


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
    danshari_score: int,
    discard_count: int,
    donate_count: int,
    keep_count: int,
    conversation_id: Optional[int] = None,
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
        conn.commit()
    return get_plan(cur.lastrowid)


def get_plan(plan_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["tasks"] = list_tasks(plan_id=plan_id)
    return d


def list_plans(status: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_conn()
    if status:
        return _rows_to_dicts(
            conn.execute(
                "SELECT * FROM plans WHERE status = ? ORDER BY id DESC", (status,)
            ).fetchall()
        )
    return _rows_to_dicts(conn.execute("SELECT * FROM plans ORDER BY id DESC").fetchall())


def update_plan_status(plan_id: int, status: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    with _lock:
        conn.execute("UPDATE plans SET status = ? WHERE id = ?", (status, plan_id))
        conn.commit()
    return get_plan(plan_id)


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
    conn = get_conn()
    with _lock:
        conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
        conn.commit()
    return get_task(task_id)


def count_done_tasks() -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM tasks WHERE status = 'done'"
    ).fetchone()
    return int(row["n"])
