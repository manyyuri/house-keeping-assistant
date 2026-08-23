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


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all passed")
