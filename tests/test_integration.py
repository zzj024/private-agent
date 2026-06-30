# tests/test_integration.py
# Responsibility: Integration tests for end-to-end system behavior

import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock


class TestChatIntegration:
    """Test chat functionality end-to-end"""

    @pytest.mark.asyncio
    async def test_simple_chat(self):
        """Test: simple chat question"""
        from app.chat_service import ChatService
        
        cs = ChatService()
        events = []
        async for event_str in cs.stream_events("What is Python?"):
            events.append(json.loads(event_str))
        
        # Should have meta, stage, final, done events
        event_types = [e['event'] for e in events]
        assert 'meta' in event_types
        assert 'done' in event_types

    @pytest.mark.asyncio
    async def test_chat_with_memory(self):
        """Test: chat with memory context"""
        from app.chat_service import ChatService
        from memory.sqlite_store import get_store
        
        # Save a memory first
        store = get_store()
        store.save_memory("name", "Xiao Ming", "preference")
        
        cs = ChatService()
        events = []
        async for event_str in cs.stream_events("What is my name?"):
            events.append(json.loads(event_str))
        
        # Should have final answer
        final_events = [e for e in events if e['event'] == 'final']
        assert len(final_events) > 0
        
        # Cleanup
        store.delete_memory("name")


class TestMemoryIntegration:
    """Test memory functionality end-to-end"""

    def test_save_and_retrieve_memory(self):
        """Test: save memory and retrieve it"""
        from memory.sqlite_store import get_store
        
        store = get_store()
        
        # Save
        store.save_memory("tech_stack", "Java", "preference")
        
        # Retrieve
        memories = store.list_memories()
        found = False
        for m in memories:
            if m["key"] == "tech_stack" and m["value"] == "Java":
                found = True
                break
        assert found
        
        # Cleanup
        store.delete_memory("tech_stack")

    def test_delete_memory(self):
        """Test: delete memory"""
        from memory.sqlite_store import get_store
        
        store = get_store()
        
        # Save
        store.save_memory("to_delete", "value", "preference")
        
        # Delete
        success = store.delete_memory("to_delete")
        assert success
        
        # Verify deleted
        memory = store.get_memory("to_delete")
        assert memory is None


class TestKnowledgeIntegration:
    """Test knowledge base functionality end-to-end"""

    def test_search_knowledge(self):
        """Test: search knowledge base"""
        from tools.knowledge_tools import search_knowledge
        
        # This will use real knowledge base if available
        result = search_knowledge("Python")
        
        # Should return something (even if empty)
        assert isinstance(result, str)


class TestReActIntegration:
    """Test ReAct loop end-to-end"""

    @pytest.mark.asyncio
    async def test_react_with_tool_calls(self):
        """Test: ReAct loop with tool calls"""
        from app.chat_service import ChatService
        
        cs = ChatService()
        events = []
        async for event_str in cs.stream_events("Remember that my name is Test"):
            events.append(json.loads(event_str))
        
        # Should have stage events (tool execution)
        stage_events = [e for e in events if e['event'] == 'stage']
        assert len(stage_events) > 0
