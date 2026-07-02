"""Test passive memory extraction logic (LLM mocked)."""
import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from memory.sqlite_store import SqliteStore


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    return SqliteStore(tmp_path / "test.db")


class TestFormatMessages:
    def test_format(self):
        from memory.passive_extractor import _format_messages
        msgs = [
            {"id": 1, "role": "user", "content": "Hello"},
            {"id": 2, "role": "assistant", "content": "Hi"},
        ]
        result = _format_messages(msgs)
        assert "[User]: Hello" in result
        assert "[Assistant]: Hi" in result

    def test_empty(self):
        from memory.passive_extractor import _format_messages
        assert _format_messages([]) == ""


class TestExtractJson:
    def test_direct_json(self):
        from memory.passive_extractor import _extract_json
        assert _extract_json('{"a": 1}') == {"a": 1}

    def test_code_block(self):
        from memory.passive_extractor import _extract_json
        result = _extract_json('```json\n{"a": 1}\n```')
        assert result == {"a": 1}

    def test_braced_json(self):
        from memory.passive_extractor import _extract_json
        result = _extract_json('some text {"a": 1} more text')
        assert result == {"a": 1}

    def test_invalid(self):
        from memory.passive_extractor import _extract_json
        assert _extract_json("not json") is None
        assert _extract_json("") is None
        assert _extract_json(None) is None


class TestExtractionPipeline:
    def test_extracts_candidates(self, store):
        from memory.passive_extractor import extract_passive_memories

        conv_id = store.create_conversation("test")
        store.save_message(conv_id, "user", "My name is Xiao Ming")
        store.save_message(conv_id, "assistant", "Hello Xiao Ming")
        store.save_message(conv_id, "user", "I use Python for all my projects")

        # v0.5: high-confidence (>=0.85) → auto_accepted, mid (0.6-0.85) → pending
        mock_response = json.dumps({
            "memories": [
                {"key": "user_name", "value": "Xiao Ming",
                 "category": "personal", "confidence": 0.95,
                 "importance": 0.8, "sensitivity": "medium",
                 "action": "store",
                 "evidence": "My name is Xiao Ming",
                 "reason": "User identity"},
                {"key": "tech_stack_python", "value": "Python",
                 "category": "tech_stack", "confidence": 0.7,
                 "importance": 0.85, "sensitivity": "low",
                 "action": "store",
                 "evidence": "I use Python for all my projects",
                 "reason": "Tech stack"},
            ]
        })

        mock_client = MagicMock()
        mock_client.chat.return_value = mock_response

        with patch("memory.sqlite_store.get_store", return_value=store):
            with patch("llm.ollama_client.get_ollama_client",
                       return_value=mock_client):
                extract_passive_memories(conv_id)

        # One auto_accepted (0.95), one pending (0.7)
        auto_ok = store.list_memory_candidates("auto_accepted")
        pending = store.list_memory_candidates("pending")
        assert len(auto_ok) == 1
        assert len(pending) == 1
        assert auto_ok[0]["key"] == "user_name"
        assert pending[0]["key"] == "tech_stack_python"

    def test_skips_forget_actions(self, store):
        from memory.passive_extractor import extract_passive_memories

        conv_id = store.create_conversation("test")
        store.save_message(conv_id, "user", "blah")

        # v0.5: confidence 0.7 falls in mid range → pending
        mock_response = json.dumps({
            "memories": [
                {"key": "skip", "value": "x", "action": "forget",
                 "confidence": 0.5, "importance": 0.5},
                {"key": "keep", "value": "y", "action": "store",
                 "confidence": 0.7, "importance": 0.5},
            ]
        })
        mock_client = MagicMock()
        mock_client.chat.return_value = mock_response

        with patch("memory.sqlite_store.get_store", return_value=store):
            with patch("llm.ollama_client.get_ollama_client",
                       return_value=mock_client):
                extract_passive_memories(conv_id)

        pending = store.list_memory_candidates("pending")
        assert len(pending) == 1
        assert pending[0]["key"] == "keep"

    def test_empty_response(self, store):
        from memory.passive_extractor import extract_passive_memories

        conv_id = store.create_conversation("test")
        store.save_message(conv_id, "user", "OK")

        mock_response = json.dumps({"memories": []})
        mock_client = MagicMock()
        mock_client.chat.return_value = mock_response

        with patch("memory.sqlite_store.get_store", return_value=store):
            with patch("llm.ollama_client.get_ollama_client",
                       return_value=mock_client):
                extract_passive_memories(conv_id)

        assert store.list_memory_candidates("pending") == []

    def test_llm_error_graceful(self, store):
        from memory.passive_extractor import extract_passive_memories

        conv_id = store.create_conversation("test")
        store.save_message(conv_id, "user", "Hello")

        mock_client = MagicMock()
        mock_client.chat.side_effect = RuntimeError("Ollama down")

        with patch("memory.sqlite_store.get_store", return_value=store):
            with patch("llm.ollama_client.get_ollama_client",
                       return_value=mock_client):
                extract_passive_memories(conv_id)  # must not raise

        assert store.list_memory_candidates("pending") == []

    def test_no_messages_skips(self, store):
        from memory.passive_extractor import extract_passive_memories

        conv_id = store.create_conversation("test")
        # no messages

        mock_client = MagicMock()
        with patch("memory.sqlite_store.get_store", return_value=store):
            with patch("llm.ollama_client.get_ollama_client",
                       return_value=mock_client):
                extract_passive_memories(conv_id)

        mock_client.chat.assert_not_called()


class TestScheduling:
    def test_schedule_creates_timer(self):
        from memory.passive_extractor import (
            schedule_passive_memory_extraction, _pending_timers)
        _pending_timers.clear()
        schedule_passive_memory_extraction(1, delay_seconds=0)
        assert 1 in _pending_timers
        _pending_timers[1].cancel()

    def test_schedule_debounces(self):
        from memory.passive_extractor import (
            schedule_passive_memory_extraction, _pending_timers)
        _pending_timers.clear()
        schedule_passive_memory_extraction(1, delay_seconds=60)
        first = _pending_timers[1]
        schedule_passive_memory_extraction(1, delay_seconds=60)
        second = _pending_timers[1]
        assert second is not first
        second.cancel()

    def test_disabled_when_false(self):
        from memory.passive_extractor import (
            schedule_passive_memory_extraction, _pending_timers)
        from config.settings import settings

        _pending_timers.clear()
        original = settings.passive_memory_enabled
        settings.passive_memory_enabled = False
        try:
            schedule_passive_memory_extraction(1)
            assert 1 not in _pending_timers
        finally:
            settings.passive_memory_enabled = original
