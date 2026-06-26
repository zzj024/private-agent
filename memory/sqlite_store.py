# 职责：SQLite 数据库的读写封装
# 所有数据库操作都通过这个模块，不直接写 SQL 散在各处

import sqlite3
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

class SqliteStore:
    """sqlite存储封装，提供记忆和会话的crud操作"""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化数据库：创建表结构"""
        schema_path = Path(__file__).parent / "schema.sql"
        with self._connect() as conn:
            conn.executescript(schema_path.read_text(encoding="utf-8"))

    def _connect(self) -> sqlite3.Connection:
        """获取数据库连接，每次调用都是新连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def save_memory(self, key: str, value: str, category: str = "") -> dict:
        """保存一条长期记忆，key重复则更新"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO memories (key, value, category, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    category = excluded.category,
                    updated_at = excluded.updated_at
                """, (key, value, category, now)
            )
        return self.get_memory(key)

    def get_memory(self, key: str) -> Optional[dict]:
        """按key查询一条记忆"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE key = ?", (key,)).fetchone()
        return dict(row) if row else None

    def list_memories(self,category: Optional[str] = None) -> list[dict]:
        """列出所有记忆,可按照分类筛选"""
        with self._connect() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE category = ? " \
                    "ORDER BY updated_at DESC",
                (category,)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memories ORDER BY updated_at DESC").fetchall()
            return [dict(row) for row in rows]

    def delete_memory(self, key: str) -> bool:
        """删除一条记忆"""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM memories WHERE key = ?", (key,))
        return cursor.rowcount > 0

    def create_conversation(self, title: str = "新对话") -> int:
          """创建新会话，返回会话 ID"""
          with self._connect() as conn:
              cursor = conn.execute(
                  "INSERT INTO conversations (title) VALUES (?)", (title,)
              )
              return cursor.lastrowid

    def save_message(self, conversation_id: int, role: str, content: str):
        """保存一条消息到指定会话"""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content)"
                "VALUES (?, ?, ?)",
                (conversation_id, role, content)
            )
            conn.execute(
                "UPDATE conversations SET updated_at = datetime('now','localtime') WHERE id = ?",
                (conversation_id,)
            )

    def get_conversation_messages(self, conversation_id: int) -> list[dict]:
        """获取一个会话的所有消息"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at",
                (conversation_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_recent_conversations(self, limit: int = 10) -> list[dict]:
        """获取最近的会话列表"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ?",(limit,)
            ).fetchall()
            return [dict(r) for r in rows]

     # 快捷函数：不需要创建实例也能用
def get_store(db_path: Optional[str] = None) -> SqliteStore:
    """获取 SqliteStore 实例（后续会被依赖注入替代）"""
    if db_path is None:
        from config.settings import settings
        db_path = settings.sqlite_path
    return SqliteStore(db_path)