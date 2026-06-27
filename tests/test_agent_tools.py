# tests/test_agent_tools.py
# 职责：测试 agent/tools.py 中 5 个 @tool 工具的行为

import pytest
from unittest.mock import patch, MagicMock


class TestSearchKnowledge:
    """测试 search_knowledge 工具"""

    def test_search_returns_text(self):
        """搜索返回格式化文本"""
        from agent.tools import search_knowledge
        mock_data = '知识库结果'
        with patch('tools.knowledge_tools.search_knowledge', return_value=mock_data):
            result = search_knowledge.invoke({'query': 'test'})
            assert isinstance(result, str)
            assert len(result) > 0

    def test_search_empty_result(self):
        """搜索无结果返回空字符串"""
        from agent.tools import search_knowledge
        with patch('tools.knowledge_tools.search_knowledge', return_value=''):
            result = search_knowledge.invoke({'query': 'xyz'})
            assert result == ''

    def test_search_calls_kb_with_correct_query(self):
        """验证查询参数正确传递"""
        from agent.tools import search_knowledge
        mock_kb = MagicMock(return_value='r')
        with patch('tools.knowledge_tools.search_knowledge', mock_kb):
            search_knowledge.invoke({'query': 'Redis'})
            mock_kb.assert_called_once_with('Redis')


class TestSaveMemory:
    """测试 save_memory 工具"""

    def test_save_with_all_params(self):
        """保存记忆，传入所有参数"""
        from agent.tools import save_memory
        mock_store = MagicMock()
        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            result = save_memory.invoke({'key': 'name', 'value': 'XiaoMing', 'category': 'preference'})
            mock_store.save_memory.assert_called_once_with('name', 'XiaoMing', 'preference')
            assert '已记住' in result

    def test_save_with_default_category(self):
        """不传 category 时使用默认值 preference"""
        from agent.tools import save_memory
        mock_store = MagicMock()
        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            save_memory.invoke({'key': 'note', 'value': 'test'})
            mock_store.save_memory.assert_called_once_with('note', 'test', 'preference')


class TestListMemories:
    """测试 list_memories 工具"""

    def test_list_all_memories(self):
        """列出所有记忆"""
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
        """无记忆时返回提示"""
        from agent.tools import list_memories
        mock_store = MagicMock()
        mock_store.list_memories.return_value = []
        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            result = list_memories.invoke({})
            assert '暂无' in result or '没有' in result

    def test_list_with_category(self):
        """按分类筛选"""
        from agent.tools import list_memories
        mock_store = MagicMock()
        mock_store.list_memories.return_value = [{'key': 'goal', 'value': 'learn', 'category': 'goal'}]
        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            result = list_memories.invoke({'category': 'goal'})
            mock_store.list_memories.assert_called_once_with('goal')
            assert 'goal' in result

    def test_list_no_category_passes_none(self):
        """不传 category 时传 None"""
        from agent.tools import list_memories
        mock_store = MagicMock()
        mock_store.list_memories.return_value = []
        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            list_memories.invoke({})
            mock_store.list_memories.assert_called_once_with(None)


class TestDeleteMemory:
    """测试 delete_memory 工具"""

    def test_delete_existing_key(self):
        """删除已存在的记忆"""
        from agent.tools import delete_memory
        mock_store = MagicMock()
        mock_store.delete_memory.return_value = True
        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            result = delete_memory.invoke({'key': 'name'})
            mock_store.delete_memory.assert_called_once_with('name')
            assert '已删除' in result or 'name' in result

    def test_delete_nonexistent_key(self):
        """删除不存在的记忆"""
        from agent.tools import delete_memory
        mock_store = MagicMock()
        mock_store.delete_memory.return_value = False
        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            result = delete_memory.invoke({'key': 'nonexistent'})
            assert '未找到' in result or '不存在' in result


class TestDeleteAllMemories:
    """测试 delete_all_memories 工具"""

    def test_delete_all_memories(self):
        """删除全部记忆"""
        from agent.tools import delete_all_memories
        mock_store = MagicMock()
        mock_store.list_memories.return_value = [{'key': 'a'}, {'key': 'b'}, {'key': 'c'}]
        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            result = delete_all_memories.invoke({})
            assert mock_store.delete_memory.call_count == 3
            assert '3' in result or '全部' in result

    def test_delete_all_empty(self):
        """没有记忆时删除全部"""
        from agent.tools import delete_all_memories
        mock_store = MagicMock()
        mock_store.list_memories.return_value = []
        with patch('memory.sqlite_store.get_store', return_value=mock_store):
            result = delete_all_memories.invoke({})
            assert '0' in result or '暂无' in result or '没有' in result
