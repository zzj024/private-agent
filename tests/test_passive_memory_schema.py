"""Test that memory_candidates table and new memories columns exist."""
import pytest
from pathlib import Path
from memory.sqlite_store import SqliteStore


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    return SqliteStore(tmp_path / "test.db")


class TestMemoryCandidatesTable:
    def test_table_exists(self, store):
        with store._connect() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='memory_candidates'"
            ).fetchone()
            assert row is not None

    def test_required_columns_present(self, store):
        with store._connect() as conn:
            rows = conn.execute("PRAGMA table_info(memory_candidates)").fetchall()
            cols = {r["name"] for r in rows}
        expected = {"id", "key", "value", "category", "confidence",
                    "importance", "sensitivity", "action", "evidence",
                    "reason", "source_conversation_id", "source_message_ids",
                    "status", "created_at", "reviewed_at"}
        assert expected.issubset(cols)

    def test_default_status_is_pending(self, store):
        cid = store.insert_memory_candidate("k", "v")
        c = store.get_memory_candidate(cid)
        assert c["status"] == "pending"


class TestMemoriesMigration:
    def test_new_columns_exist(self, store):
        with store._connect() as conn:
            rows = conn.execute("PRAGMA table_info(memories)").fetchall()
            cols = {r["name"] for r in rows}
        expected = {"source", "status", "evidence",
                    "source_conversation_id", "source_message_ids",
                    "valid_from", "valid_to", "last_seen_at", "seen_count"}
        assert expected.issubset(cols)

    def test_migration_idempotent(self, store):
        """Calling migration again should not raise."""
        store._migrate_db()  # should not throw
