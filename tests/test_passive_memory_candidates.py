"""Test memory candidate CRUD operations."""
import pytest
from pathlib import Path
from memory.sqlite_store import SqliteStore


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    return SqliteStore(tmp_path / "test.db")


class TestCandidateCRUD:
    def test_insert_returns_id(self, store):
        cid = store.insert_memory_candidate("k1", "v1")
        assert isinstance(cid, int)
        assert cid > 0

    def test_get_candidate(self, store):
        cid = store.insert_memory_candidate("k1", "v1", category="pref")
        c = store.get_memory_candidate(cid)
        assert c["key"] == "k1"
        assert c["value"] == "v1"
        assert c["category"] == "pref"

    def test_get_nonexistent(self, store):
        assert store.get_memory_candidate(99999) is None

    def test_list_pending_only(self, store):
        store.insert_memory_candidate("a", "va", status="pending")
        store.insert_memory_candidate("b", "vb", status="pending")
        store.insert_memory_candidate("c", "vc", status="accepted")
        assert len(store.list_memory_candidates("pending")) == 2
        assert len(store.list_memory_candidates("accepted")) == 1

    def test_list_empty(self, store):
        assert store.list_memory_candidates("pending") == []

    def test_update_status(self, store):
        cid = store.insert_memory_candidate("k", "v")
        assert store.update_memory_candidate_status(cid, "accepted") is True
        c = store.get_memory_candidate(cid)
        assert c["status"] == "accepted"
        assert c["reviewed_at"] is not None

    def test_update_nonexistent(self, store):
        assert store.update_memory_candidate_status(99999, "accepted") is False

    def test_default_status_is_pending(self, store):
        cid = store.insert_memory_candidate("k", "v")
        assert store.get_memory_candidate(cid)["status"] == "pending"

    def test_all_fields_preserved(self, store):
        cid = store.insert_memory_candidate(
            key="test_key", value="test_value", category="tech_stack",
            confidence=0.85, importance=0.7, sensitivity="low",
            action="store", evidence="user said it", reason="useful",
            source_conversation_id=3,
            source_message_ids="[1,2]", status="pending",
        )
        c = store.get_memory_candidate(cid)
        assert c["confidence"] == 0.85
        assert c["importance"] == 0.7
        assert c["evidence"] == "user said it"
        assert c["source_conversation_id"] == 3


class TestSaveMemoryBackwardCompat:
    def test_old_signature_works(self, store):
        """save_memory("k","v","cat") must still work."""
        m = store.save_memory("key1", "value1", "cat1")
        assert m["key"] == "key1"
        assert m["value"] == "value1"
        assert m["category"] == "cat1"

    def test_default_confidence_is_1(self, store):
        m = store.save_memory("key1", "value1")
        assert m["confidence"] == 1.0

    def test_default_source_is_explicit(self, store):
        m = store.save_memory("key1", "value1")
        assert m["source"] == "explicit"

    def test_new_params_accepted(self, store):
        m = store.save_memory("key1", "value1", "cat1",
                               confidence=0.8, source="passive",
                               evidence="test ev", seen_count=3)
        assert m["confidence"] == 0.8
        assert m["source"] == "passive"
        assert m["evidence"] == "test ev"


class TestGetRecentMessages:
    def test_returns_messages_in_order(self, store):
        conv_id = store.create_conversation("test")
        store.save_message(conv_id, "user", "msg1")
        store.save_message(conv_id, "assistant", "msg2")
        store.save_message(conv_id, "user", "msg3")

        msgs = store.get_recent_messages(conv_id, limit=2)
        # Should return the 2 most recent in chronological order
        assert len(msgs) == 2
        assert msgs[0]["content"] == "msg2"
        assert msgs[1]["content"] == "msg3"

    def test_empty_conversation(self, store):
        conv_id = store.create_conversation("test")
        msgs = store.get_recent_messages(conv_id)
        assert msgs == []

    def test_respects_limit(self, store):
        conv_id = store.create_conversation("test")
        for i in range(10):
            store.save_message(conv_id, "user", f"msg{i}")

        msgs = store.get_recent_messages(conv_id, limit=3)
        assert len(msgs) == 3
