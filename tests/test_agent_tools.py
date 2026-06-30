# tests/test_agent_tools.py
# Responsibility: Test 5 @tool tools in agent/tools.py

import pytest
from unittest.mock import patch, MagicMock


class TestSearchKnowledge:
    """Test search_knowledge tool"""

    def test_search_returns_text(self):
        """Search returns formatted text"""
        from agent.tools import search_knowledge
        mock_data = 'Knowledge result'
        with patch('tools.knowledge_tools.search_knowledge', return_value=mock_data):
            result = search_knowledge.invoke({'query': 'test'})
            assert isinstance(result, str)
            assert len(result) > 0

    def test_search_empty_result(self):
        """Search with no result returns empty string"""
        from agent.tools import search_knowledge
        with patch('tools.knowledge_tools.search_knowledge', return_value=''):
            result = search_knowledge.invoke({'query': 'xyz'})
            assert result == ''

    def test_search_calls_kb_with_correct_query(self):
        """Verify query parameter is passed correctly"""
        from agent.tools import search_knowledge
        mock_kb = MagicMock(return_value='r')
        with patch('tools.knowledge_tools.search_knowledge', mock_kb):
            search_knowledge.invoke({'query': 'Redis'})
            mock_kb.assert_called_once_with('Redis')


class TestSaveMemory:
    """Test save_memory tool"""

    def test_save_with_all_params(self):
        """Save memory with all parameters"""
        from agent.tools import save_memory
        mock_store = MagicMock()
        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            result = save_memory.invoke({'key': 'name', 'value': 'XiaoMing', 'category': 'preference'})
            mock_store.save_memory.assert_called_once_with('name', 'XiaoMing', 'preference')
            assert 'Saved' in result

    def test_save_with_default_category(self):
        """Default category is preference when not specified"""
        from agent.tools import save_memory
        mock_store = MagicMock()
        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            save_memory.invoke({'key': 'note', 'value': 'test'})
            mock_store.save_memory.assert_called_once_with('note', 'test', 'preference')


class TestListMemories:
    """Test list_memories tool"""

    def test_list_all_memories(self):
        """List all memories"""
        from agent.tools import list_memories
        mock_store = MagicMock()
        mock_store.list_memories.return_value = [
            {'key': 'name', 'value': 'XiaoMing', 'category': 'preference'},
            {'key': 'skill', 'value': 'Python', 'category': 'tech'},
        ]
        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            result = list_memories.invoke({})
            assert 'name' in result
            assert 'skill' in result

    def test_list_empty_memories(self):
        """No memories returns hint"""
        from agent.tools import list_memories
        mock_store = MagicMock()
        mock_store.list_memories.return_value = []
        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            result = list_memories.invoke({})
            assert 'No memories' in result

    def test_list_with_category(self):
        """Filter by category"""
        from agent.tools import list_memories
        mock_store = MagicMock()
        mock_store.list_memories.return_value = [{'key': 'goal', 'value': 'learn', 'category': 'goal'}]
        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            result = list_memories.invoke({'category': 'goal'})
            mock_store.list_memories.assert_called_once_with('goal')
            assert 'goal' in result

    def test_list_no_category_passes_none(self):
        """No category passes None"""
        from agent.tools import list_memories
        mock_store = MagicMock()
        mock_store.list_memories.return_value = []
        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            list_memories.invoke({})
            mock_store.list_memories.assert_called_once_with(None)


class TestDeleteMemory:
    """Test delete_memory tool"""

    def test_delete_existing_key(self):
        """Delete existing memory"""
        from agent.tools import delete_memory
        mock_store = MagicMock()
        mock_store.delete_memory.return_value = True
        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            result = delete_memory.invoke({'key': 'name'})
            mock_store.delete_memory.assert_called_once_with('name')
            assert 'Deleted' in result or 'name' in result

    def test_delete_nonexistent_key(self):
        """Delete nonexistent memory"""
        from agent.tools import delete_memory
        mock_store = MagicMock()
        mock_store.delete_memory.return_value = False
        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            result = delete_memory.invoke({'key': 'nonexistent'})
            assert 'not found' in result or 'not exist' in result


class TestDeleteAllMemories:
    """Test delete_all_memories tool"""

    def test_delete_all_memories(self):
        """Delete all memories"""
        from agent.tools import delete_all_memories
        mock_store = MagicMock()
        mock_store.list_memories.return_value = [{'key': 'a'}, {'key': 'b'}, {'key': 'c'}]
        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            result = delete_all_memories.invoke({})
            assert mock_store.delete_memory.call_count == 3
            assert '3' in result or 'all' in result

    def test_delete_all_empty(self):
        """No memories to delete"""
        from agent.tools import delete_all_memories
        mock_store = MagicMock()
        mock_store.list_memories.return_value = []
        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            result = delete_all_memories.invoke({})
            assert 'No memories' in result
