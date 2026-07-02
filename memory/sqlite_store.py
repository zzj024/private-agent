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
        self._migrate_db()

    def _migrate_db(self):
        """给旧数据库补加新列，列已存在则跳过"""
        migrations = [
            "ALTER TABLE memories ADD COLUMN source TEXT DEFAULT 'explicit'",
            "ALTER TABLE memories ADD COLUMN status TEXT DEFAULT 'active'",
            "ALTER TABLE memories ADD COLUMN evidence TEXT DEFAULT ''",
            "ALTER TABLE memories ADD COLUMN source_conversation_id INTEGER",
            "ALTER TABLE memories ADD COLUMN source_message_ids TEXT DEFAULT '[]'",
            "ALTER TABLE memories ADD COLUMN valid_from TEXT",
            "ALTER TABLE memories ADD COLUMN valid_to TEXT",
            "ALTER TABLE memories ADD COLUMN last_seen_at TEXT",
            "ALTER TABLE memories ADD COLUMN seen_count INTEGER DEFAULT 1",
        ]
        with self._connect() as conn:
            for sql in migrations:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError:
                    pass  # 列已存在，跳过

    def _connect(self) -> sqlite3.Connection:
        """获取数据库连接，每次调用都是新连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def save_memory(self, key: str, value: str, category: str = "",
                    confidence: float = 1.0, source: str = "explicit",
                    evidence: str = "",
                    source_conversation_id: int | None = None,
                    source_message_ids: str | None = None,
                    seen_count: int = 1) -> dict:
        """保存一条长期记忆，key重复则更新。

        新增参数全部带默认值，旧的 save_memory("k","v","cat") 行为不变。
        """
        source_message_ids = source_message_ids or '[]'
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO memories (
                    key, value, category, confidence, source, status,
                    evidence, source_conversation_id, source_message_ids,
                    last_seen_at, seen_count, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    category = excluded.category,
                    confidence = excluded.confidence,
                    updated_at = excluded.updated_at,
                    last_seen_at = excluded.last_seen_at,
                    seen_count = memories.seen_count + 1
                """, (
                    key, value, category, confidence, source, evidence,
                    source_conversation_id, source_message_ids,
                    now, seen_count, now,
                ))
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

    def get_recent_conversations(self, limit: int = 20) -> list[dict]:
        """获取最近的会话列表"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ?",(limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_recent_messages(self, conversation_id: int, limit: int = 12) -> list[dict]:
        """取某个会话最近 N 条消息，返回时间正序（旧→新）"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (conversation_id, limit)
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def insert_memory_candidate(self, key: str, value: str,
                                 category: str = "",
                                 confidence: float = 0.5,
                                 importance: float = 0.5,
                                 sensitivity: str = "low",
                                 action: str = "store",
                                 evidence: str = "",
                                 reason: str = "",
                                 source_conversation_id: int | None = None,
                                 source_message_ids: str = "[]",
                                 status: str = "pending") -> int:
        """插入一条候选记忆，返回 id"""
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO memory_candidates ("
                "key, value, category, confidence, importance, sensitivity, "
                "action, evidence, reason, source_conversation_id, "
                "source_message_ids, status"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (key, value, category, confidence, importance, sensitivity,
                 action, evidence, reason, source_conversation_id,
                 source_message_ids, status)
            )
            return cursor.lastrowid

    def list_memory_candidates(self, status: str = "pending") -> list[dict]:
        """列出候选记忆，按状态筛选"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_candidates WHERE status = ? "
                "ORDER BY created_at DESC",
                (status,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_memory_candidate(self, candidate_id: int) -> dict | None:
        """查一条候选记忆"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_candidates WHERE id = ?",
                (candidate_id,)
            ).fetchone()
            return dict(row) if row else None

    def update_memory_candidate_status(self, candidate_id: int,
                                        status: str) -> bool:
        """更新候选状态，自动写入 reviewed_at"""
        reviewed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE memory_candidates SET status = ?, reviewed_at = ? "
                "WHERE id = ?",
                (status, reviewed_at, candidate_id)
            )
            return cursor.rowcount > 0

    def update_memory_candidate(self, candidate_id: int, key: str = None,
                                 value: str = None, category: str = None) -> bool:
        """Update candidate fields before accepting"""
        fields = {}
        if key is not None:
            fields["key"] = key
        if value is not None:
            fields["value"] = value
        if category is not None:
            fields["category"] = category
        if not fields:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [candidate_id]
        with self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE memory_candidates SET {set_clause} WHERE id = ?",
                vals
            )
            return cursor.rowcount > 0

    def get_messages_by_ids(self, message_ids: list[int]) -> list[dict]:
        """Batch get messages by their IDs"""
        if not message_ids:
            return []
        placeholders = ",".join("?" for _ in message_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM messages WHERE id IN ({placeholders}) "
                f"ORDER BY id",
                message_ids
            ).fetchall()
            return [dict(r) for r in rows]

    def get_conversation(self, conversation_id: int) -> dict | None:
        """获取单个会话信息"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            return dict(row) if row else None

    def rename_conversation(self, conversation_id: int, title: str) -> bool:
        """重命名会话"""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE conversations SET title = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                (title, conversation_id),
            )
            return cursor.rowcount > 0

    def delete_conversation(self, conversation_id: int) -> bool:
        """删除会话及其所有消息（CASCADE）"""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM conversations WHERE id = ?", (conversation_id,)
            )
            return cursor.rowcount > 0

     # 快捷函数：不需要创建实例也能用

def get_store(db_path: Optional[str] = None) -> SqliteStore:
    """获取 SqliteStore 实例（后续会被依赖注入替代）"""
    if db_path is None:
        from config.settings import settings
        db_path = settings.sqlite_path
    return SqliteStore(db_path)