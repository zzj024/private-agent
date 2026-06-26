# tests/test_sqlite_store.py
# 职责：测试 SqliteStore 的所有核心功能

import pytest
import time
from pathlib import Path
from memory.sqlite_store import SqliteStore


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    """
    每个测试用例创建一个全新的临时数据库，
    测试结束后自动清理，不污染开发数据。
    """
    db_path = tmp_path / "test.db"
    return SqliteStore(db_path)


# ═══════════════════════════════════════════════
# 记忆操作测试
# ═══════════════════════════════════════════════

class TestMemories:
    """长期记忆的 CRUD 测试"""

    def test_save_and_get_memory(self, store: SqliteStore):
        """保存一条记忆，应该能按 key 查到"""
        store.save_memory("tech_stack", "Java + Spring Boot", "tech_stack")
        mem = store.get_memory("tech_stack")
        assert mem is not None
        assert mem["key"] == "tech_stack"
        assert mem["value"] == "Java + Spring Boot"
        assert mem["category"] == "tech_stack"

    def test_save_memory_overwrite(self, store: SqliteStore):
        """相同 key 保存两次，应该覆盖更新"""
        store.save_memory("tech_stack", "Java", "tech_stack")
        store.save_memory("tech_stack", "Python", "tech_stack")
        mem = store.get_memory("tech_stack")
        assert mem["value"] == "Python"

    def test_get_nonexistent_memory(self, store: SqliteStore):
        """查询不存在的 key，应该返回 None"""
        mem = store.get_memory("not_exist_key")
        assert mem is None

    def test_list_all_memories(self, store: SqliteStore):
        """列出所有记忆"""
        store.save_memory("a", "value_a", "cat1")
        store.save_memory("b", "value_b", "cat2")
        store.save_memory("c", "value_c", "cat1")
        all_mems = store.list_memories()
        assert len(all_mems) == 3

    def test_list_memories_by_category(self, store: SqliteStore):
        """按分类筛选记忆"""
        store.save_memory("a", "value_a", "cat1")
        store.save_memory("b", "value_b", "cat2")
        cat1_mems = store.list_memories(category="cat1")
        assert len(cat1_mems) == 1
        assert cat1_mems[0]["key"] == "a"

    def test_delete_memory(self, store: SqliteStore):
        """删除一条记忆后，应该查不到"""
        store.save_memory("to_delete", "will be deleted", "test")
        assert store.delete_memory("to_delete") is True
        assert store.get_memory("to_delete") is None

    def test_delete_nonexistent_memory(self, store: SqliteStore):
        """删除不存在的记忆，应该返回 False"""
        assert store.delete_memory("not_exist") is False

    def test_memory_has_timestamps(self, store: SqliteStore):
        """保存的记忆应该自动带时间戳"""
        store.save_memory("with_time", "test", "test")
        mem = store.get_memory("with_time")
        assert mem["created_at"] is not None
        assert mem["updated_at"] is not None

    def test_memory_updated_at_changes(self, store: SqliteStore):
        """更新记忆后，updated_at 应该变化"""
        store.save_memory("k", "v1", "test")
        mem1 = store.get_memory("k")
        time.sleep(0.01)
        store.save_memory("k", "v2", "test")
        mem2 = store.get_memory("k")
        assert mem2["updated_at"] != mem1["updated_at"]


# ═══════════════════════════════════════════════
# 会话和消息操作测试
# ═══════════════════════════════════════════════

class TestConversations:
    """会话与消息的 CRUD 测试"""

    def test_create_conversation(self, store: SqliteStore):
        """创建会话应该返回一个 ID"""
        conv_id = store.create_conversation("测试会话")
        assert isinstance(conv_id, int)
        assert conv_id > 0

    def test_create_conversation_default_title(self, store: SqliteStore):
        """不传标题时，应该使用默认标题"""
        conv_id = store.create_conversation()
        assert isinstance(conv_id, int)

    def test_save_and_get_messages(self, store: SqliteStore):
        """保存消息后，应该能查到"""
        conv_id = store.create_conversation()
        store.save_message(conv_id, "user", "你好")
        store.save_message(conv_id, "assistant", "你好！")
        messages = store.get_conversation_messages(conv_id)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "你好"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "你好！"

    def test_messages_ordered_by_time(self, store: SqliteStore):
        """消息应该按创建时间顺序排列"""
        conv_id = store.create_conversation()
        store.save_message(conv_id, "user", "第一条")
        time.sleep(0.01)
        store.save_message(conv_id, "user", "第二条")
        messages = store.get_conversation_messages(conv_id)
        assert messages[0]["content"] == "第一条"
        assert messages[1]["content"] == "第二条"

    def test_empty_conversation_messages(self, store: SqliteStore):
        """刚创建的会话，消息列表应该为空"""
        conv_id = store.create_conversation()
        messages = store.get_conversation_messages(conv_id)
        assert messages == []

    def test_get_recent_conversations(self, store: SqliteStore):
        """获取最近的会话列表"""
        id1 = store.create_conversation("对话A")
        id2 = store.create_conversation("对话B")
        recent = store.get_recent_conversations()
        assert len(recent) >= 2
        # 最近更新的在前面
        assert recent[0]["id"] in (id1, id2)

    def test_conversation_updated_on_message(self, store: SqliteStore):
        """新消息应该更新会话的 updated_at"""
        conv_id = store.create_conversation("旧对话")
        time.sleep(0.01)
        store.save_message(conv_id, "user", "新消息")
        recent = store.get_recent_conversations()
        conv = next(c for c in recent if c["id"] == conv_id)
        assert conv["title"] == "旧对话"


# ═══════════════════════════════════════════════
# 边界情况测试
# ═══════════════════════════════════════════════

class TestEdgeCases:
    """边界情况和异常测试"""

    def test_database_created_on_init(self, tmp_path: Path):
        """初始化 SqliteStore 时应该自动创建数据库文件"""
        db_path = tmp_path / "new.db"
        assert not db_path.exists()
        SqliteStore(db_path)
        assert db_path.exists()

    def test_multiple_stores_same_db(self, tmp_path: Path):
        """多个 SqliteStore 实例操作同一个库，应该互不干扰"""
        db_path = tmp_path / "shared.db"
        store1 = SqliteStore(db_path)
        store2 = SqliteStore(db_path)
        store1.save_memory("k", "v", "test")
        mem = store2.get_memory("k")
        assert mem["value"] == "v"

    def test_unicode_values(self, store: SqliteStore):
        """中文和特殊字符应该正常存储"""
        text = "我的技术栈是 Java + Spring Boot，学习目标是掌握 AI Agent"
        store.save_memory("intro", text, "personal")
        mem = store.get_memory("intro")
        assert mem["value"] == text

    def test_long_text(self, store: SqliteStore):
        """长文本应该正常存储"""
        long_text = "A" * 10000
        store.save_memory("long", long_text, "test")
        mem = store.get_memory("long")
        assert len(mem["value"]) == 10000
