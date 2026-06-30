# tests/test_tools.py
# Responsibility: Unit tests for tool functions

import pytest
from unittest.mock import patch, MagicMock

from agent.tools import (
    search_knowledge,
    save_memory,
    list_memories,
    delete_memory,
    delete_all_memories,
    TOOLS,
)


# ═══════════════════════════════════════════════
# Test search_knowledge
# ═══════════════════════════════════════════════

class TestSearchKnowledge:
    """Test search_knowledge tool"""

    @patch("tools.knowledge_tools.search_knowledge")
    def test_search_returns_result(self, mock_search):
        """Test: search returns result"""
        # Prepare
        mock_search.return_value = "K1: Redis is in-memory database"
        
        # Execute
        result = search_knowledge.invoke({"query": "Redis"})
        
        # Verify
        assert "Redis" in result
        mock_search.assert_called_once_with("Redis")

    @patch("tools.knowledge_tools.search_knowledge")
    def test_search_empty_query(self, mock_search):
        """Test: empty query"""
        # Prepare
        mock_search.return_value = ""
        
        # Execute
        result = search_knowledge.invoke({"query": ""})
        
        # Verify
        assert result == ""


# ═══════════════════════════════════════════════
# Test save_memory
# ═══════════════════════════════════════════════

class TestSaveMemory:
    """Test save_memory tool"""

    @patch("memory.sqlite_store.get_store")
    def test_save_memory_success(self, mock_get_store):
        """Test: save memory success"""
        # Prepare
        mock_store = MagicMock()
        mock_get_store.return_value = mock_store
        
        # Execute
        result = save_memory.invoke({
            "key": "name",
            "value": "Xiao Ming",
            "category": "preference"
        })
        
        # Verify
        assert "Saved: name = Xiao Ming" in result
        mock_store.save_memory.assert_called_once_with("name", "Xiao Ming", "preference")

    @patch("memory.sqlite_store.get_store")
    def test_save_memory_default_category(self, mock_get_store):
        """Test: default category"""
        # Prepare
        mock_store = MagicMock()
        mock_get_store.return_value = mock_store
        
        # Execute
        result = save_memory.invoke({
            "key": "tech_stack",
            "value": "Java"
        })
        
        # Verify
        mock_store.save_memory.assert_called_once_with("tech_stack", "Java", "preference")


# ═══════════════════════════════════════════════
# Test list_memories
# ═══════════════════════════════════════════════

class TestListMemories:
    """Test list_memories tool"""

    @patch("memory.sqlite_store.get_store")
    def test_list_memories_with_data(self, mock_get_store):
        """Test: has memory data"""
        # Prepare
        mock_store = MagicMock()
        mock_get_store.return_value = mock_store
        mock_store.list_memories.return_value = [
            {"key": "name", "value": "Xiao Ming", "category": "preference"},
            {"key": "tech_stack", "value": "Java", "category": "preference"},
        ]
        
        # Execute
        result = list_memories.invoke({})
        
        # Verify
        assert "name: Xiao Ming" in result
        assert "tech_stack: Java" in result

    @patch("memory.sqlite_store.get_store")
    def test_list_memories_empty(self, mock_get_store):
        """Test: no memory data"""
        # Prepare
        mock_store = MagicMock()
        mock_get_store.return_value = mock_store
        mock_store.list_memories.return_value = []
        
        # Execute
        result = list_memories.invoke({})
        
        # Verify
        assert "No memories" in result

    @patch("memory.sqlite_store.get_store")
    def test_list_memories_with_category(self, mock_get_store):
        """Test: filter by category"""
        # Prepare
        mock_store = MagicMock()
        mock_get_store.return_value = mock_store
        mock_store.list_memories.return_value = [
            {"key": "name", "value": "Xiao Ming", "category": "preference"},
        ]
        
        # Execute
        result = list_memories.invoke({"category": "preference"})
        
        # Verify
        mock_store.list_memories.assert_called_once_with("preference")


# ═══════════════════════════════════════════════
# Test delete_memory
# ═══════════════════════════════════════════════

class TestDeleteMemory:
    """Test delete_memory tool"""

    @patch("memory.sqlite_store.get_store")
    def test_delete_memory_success(self, mock_get_store):
        """Test: delete success"""
        # Prepare
        mock_store = MagicMock()
        mock_get_store.return_value = mock_store
        mock_store.delete_memory.return_value = True
        
        # Execute
        result = delete_memory.invoke({"key": "name"})
        
        # Verify
        assert "Deleted memory: name" in result
        mock_store.delete_memory.assert_called_once_with("name")

    @patch("memory.sqlite_store.get_store")
    def test_delete_memory_not_found(self, mock_get_store):
        """Test: delete failed (not found)"""
        # Prepare
        mock_store = MagicMock()
        mock_get_store.return_value = mock_store
        mock_store.delete_memory.return_value = False
        
        # Execute
        result = delete_memory.invoke({"key": "not_exist"})
        
        # Verify
        assert "Memory not found: not_exist" in result


# ═══════════════════════════════════════════════
# Test delete_all_memories
# ═══════════════════════════════════════════════

class TestDeleteAllMemories:
    """Test delete_all_memories tool"""

    @patch("memory.sqlite_store.get_store")
    def test_delete_all_success(self, mock_get_store):
        """Test: delete all success"""
        # Prepare
        mock_store = MagicMock()
        mock_get_store.return_value = mock_store
        mock_store.list_memories.return_value = [
            {"key": "name", "value": "Xiao Ming"},
            {"key": "tech_stack", "value": "Java"},
        ]
        
        # Execute
        result = delete_all_memories.invoke({})
        
        # Verify
        assert "Deleted all 2 memories" in result
        assert mock_store.delete_memory.call_count == 2

    @patch("memory.sqlite_store.get_store")
    def test_delete_all_empty(self, mock_get_store):
        """Test: no memories to delete"""
        # Prepare
        mock_store = MagicMock()
        mock_get_store.return_value = mock_store
        mock_store.list_memories.return_value = []
        
        # Execute
        result = delete_all_memories.invoke({})
        
        # Verify
        assert "No memories to delete" in result


# ═══════════════════════════════════════════════
# Test TOOLS list
# ═══════════════════════════════════════════════

class TestToolsList:
    """Test TOOLS list"""

    def test_tools_count(self):
        """Test: tool count"""
        assert len(TOOLS) == 5

    def test_tools_names(self):
        """Test: tool names"""
        tool_names = [tool.name for tool in TOOLS]
        assert "search_knowledge" in tool_names
        assert "save_memory" in tool_names
        assert "list_memories" in tool_names
        assert "delete_memory" in tool_names
        assert "delete_all_memories" in tool_names
