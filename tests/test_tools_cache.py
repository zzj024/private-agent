# tests/test_tools_cache.py
# Unit tests for tool-layer cache integration (mock-backed)

import pytest
from unittest.mock import patch, MagicMock

from agent.reflexion import ReflexionState, set_current_state, get_current_state


# ═══════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════

@pytest.fixture(autouse=True)
def clean_context():
    """Ensure context var is clean before/after each test"""
    set_current_state(None)
    yield
    set_current_state(None)


# ═══════════════════════════════════════════════
# search_knowledge with cache
# ═══════════════════════════════════════════════

class TestSearchKnowledgeCache:
    """search_knowledge tool uses data_cache"""

    def test_cache_hit_returns_cached(self):
        """When data is cached, skip ChromaDB call"""
        state = ReflexionState()
        state.cache_tool_result("kb_v2", "test query", "[K1] Cached result")
        set_current_state(state)

        from agent.tools import search_knowledge

        with patch('tools.knowledge_tools.search_knowledge') as mock_kb:
            result = search_knowledge.invoke({"query": "test query"})
            # Should not call the actual KB
            mock_kb.assert_not_called()

        assert result == "[K1] Cached result"

    def test_cache_miss_calls_kb(self):
        """When data is not cached, call ChromaDB"""
        state = ReflexionState()
        set_current_state(state)

        from agent.tools import search_knowledge

        with patch('tools.knowledge_tools.search_knowledge', return_value="[K1] Fresh"):
            result = search_knowledge.invoke({"query": "new query"})

        assert result == "[K1] Fresh"
        # Should also be cached for next time
        assert state.get_cached_tool_result("kb_v2", "new query") == "[K1] Fresh"

    def test_no_state_calls_kb_directly(self):
        """Without ReflexionState (v0.2 mode), call KB directly"""
        set_current_state(None)

        from agent.tools import search_knowledge

        with patch('tools.knowledge_tools.search_knowledge', return_value="[K1] Direct"):
            result = search_knowledge.invoke({"query": "q"})

        assert result == "[K1] Direct"


# ═══════════════════════════════════════════════
# list_memories with cache
# ═══════════════════════════════════════════════

class TestListMemoriesCache:
    """list_memories tool uses data_cache"""

    def test_cache_hit(self):
        state = ReflexionState()
        state.cache_tool_result("memory", "memory:list:", "- tech: Java (tech_stack)")
        set_current_state(state)

        from agent.tools import list_memories
        mock_store = MagicMock()

        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            result = list_memories.invoke({"category": ""})
            # Should not query DB
            mock_store.list_memories.assert_not_called()

        assert "Java" in result

    def test_cache_miss_calls_db(self):
        state = ReflexionState()
        set_current_state(state)

        from agent.tools import list_memories
        mock_store = MagicMock()
        mock_store.list_memories.return_value = [
            {"key": "name", "value": "Alice", "category": "preference"}
        ]

        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            result = list_memories.invoke({"category": ""})

        assert "Alice" in result
        # Should be cached
        assert state.get_cached_tool_result("memory", "memory:list:") is not None


# ═══════════════════════════════════════════════
# Cache invalidation on write operations
# ═══════════════════════════════════════════════

class TestCacheInvalidation:
    """Write operations clear related cache"""

    def test_save_memory_clears_memory_cache(self):
        state = ReflexionState()
        state.cache_tool_result("memory", "memory:list:", "cached memories")
        state.cache_tool_result("kb_v2", "some query", "cached kb")
        set_current_state(state)

        from agent.tools import save_memory
        mock_store = MagicMock()

        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            save_memory.invoke({"key": "new_key", "value": "val", "category": "test"})

        # Memory cache cleared
        assert state.get_cached_tool_result("memory", "memory:list:") is None
        # KB cache untouched
        assert state.get_cached_tool_result("kb_v2", "some query") == "cached kb"

    def test_delete_memory_clears_memory_cache(self):
        state = ReflexionState()
        state.cache_tool_result("memory", "memory:list:", "cached")
        state.cache_tool_result("kb_v2", "query", "kb data")
        set_current_state(state)

        from agent.tools import delete_memory
        mock_store = MagicMock()
        mock_store.delete_memory.return_value = True

        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            delete_memory.invoke({"key": "old_key"})

        assert state.get_cached_tool_result("memory", "memory:list:") is None
        assert state.get_cached_tool_result("kb_v2", "query") == "kb data"

    def test_delete_all_memories_clears_memory_cache(self):
        state = ReflexionState()
        state.cache_tool_result("memory", "memory:list:", "cached")
        state.cache_tool_result("memory", "memory:list:tech_stack", "cached_tech")
        set_current_state(state)

        from agent.tools import delete_all_memories
        mock_store = MagicMock()
        mock_store.list_memories.return_value = [
            {"key": "m1", "value": "v1"},
            {"key": "m2", "value": "v2"},
        ]

        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            delete_all_memories.invoke({})

        # All memory-related cache cleared
        assert state.get_cached_tool_result("memory", "memory:list:") is None
        assert state.get_cached_tool_result("memory", "memory:list:tech_stack") is None
