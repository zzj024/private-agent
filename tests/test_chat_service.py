# tests/test_chat_service.py
# Responsibility: Test ChatService class

import pytest
import json
from unittest.mock import patch, AsyncMock, MagicMock


class _AsyncIter:
    def __init__(self, items):
        self._items = list(items)
    def __aiter__(self):
        return self
    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


class TestChatServiceEvents:

    def test_make_event_format(self):
        from app.chat_service import ChatService
        cs = ChatService()
        event_str = cs._make_event('meta', {'request_id': 'abc', 'thread_id': '123'})
        event = json.loads(event_str)
        assert event['event'] == 'meta'
        assert event['data']['request_id'] == 'abc'

    def test_make_event_unicode_safe(self):
        from app.chat_service import ChatService
        cs = ChatService()
        event_str = cs._make_event('stage', {'stage': 'Analyzing...', 'message': 'Checking...'})
        event = json.loads(event_str)
        assert event['data']['stage'] == 'Analyzing...'

    def test_convert_on_chain_start_to_stage(self):
        from app.chat_service import ChatService
        cs = ChatService()
        raw = {'event': 'on_chain_start', 'name': 'agent', 'data': {'input': {'message': 'hello'}}}
        result = cs._convert_langgraph_event(raw)
        event = json.loads(result)
        assert event['event'] == 'stage'
        # ChatService uses Chinese stage names
        assert event['data']['stage'] != ''

    def test_convert_on_chain_end_to_final(self):
        from app.chat_service import ChatService
        cs = ChatService()
        raw = {'event': 'on_chain_end', 'data': {'output': {'messages': [MagicMock(content='This is the final answer', tool_calls=[])]}}}
        result = cs._convert_langgraph_event(raw)
        event = json.loads(result)
        assert event['event'] == 'final'
        assert event['data']['content'] == 'This is the final answer'

    def test_convert_on_chain_error_to_error(self):
        from app.chat_service import ChatService
        cs = ChatService()
        raw = {'event': 'on_chain_error', 'data': {'error': 'Ollama connection refused'}}
        result = cs._convert_langgraph_event(raw)
        event = json.loads(result)
        assert event['event'] == 'error'
        assert 'Ollama' in event['data']['message']
        assert event['data']['retryable'] is True

    def test_unknown_event_returns_none(self):
        from app.chat_service import ChatService
        cs = ChatService()
        result = cs._convert_langgraph_event({'event': 'on_custom_event', 'data': {}})
        assert result is None


class TestChatServiceStream:

    @pytest.mark.asyncio
    @patch('agent.graph.run_agent_with_reflexion', return_value=None)
    async def test_stream_emits_meta_first(self, _mock_reflexion):
        from app.chat_service import ChatService
        cs = ChatService()
        cs.graph = MagicMock()
        cs.graph.astream_events.return_value = _AsyncIter([])
        events = [json.loads(e) async for e in cs.stream_events('hello')]
        assert len(events) > 0
        assert events[0]['event'] == 'meta'

    @pytest.mark.asyncio
    @patch('agent.graph.run_agent_with_reflexion', return_value=None)
    async def test_stream_passes_graph_events_through(self, _mock_reflexion):
        from app.chat_service import ChatService
        mock_events = [
            {'event': 'on_chain_start', 'name': 'agent', 'data': {'input': {}}},
            {'event': 'on_chain_end', 'data': {'output': {'messages': [MagicMock(content='Hello!', tool_calls=[])]}}},
        ]
        cs = ChatService()
        cs.graph = MagicMock()
        cs.graph.astream_events.return_value = _AsyncIter(mock_events)
        events = [json.loads(e) async for e in cs.stream_events('hello')]
        types = [e['event'] for e in events]
        assert types == ['meta', 'stage', 'stage', 'final', 'done']  # reflexion stage + ReAct stage

    @pytest.mark.asyncio
    @patch('agent.graph.run_agent_with_reflexion', return_value=None)
    async def test_stream_conversation_id_matches(self, _mock_reflexion):
        from app.chat_service import ChatService
        cs = ChatService()
        cs.graph = MagicMock()
        cs.graph.astream_events.return_value = _AsyncIter([])
        events = [json.loads(e) async for e in cs.stream_events('hello', conversation_id='42')]
        assert events[0]['event'] == 'meta'
        assert events[0]['data']['thread_id'] == '42'

    @pytest.mark.asyncio
    @patch('agent.graph.run_agent_with_reflexion', return_value='Reflexion answer')
    async def test_stream_reflexion_success_path(self, _mock_reflexion):
        """When reflexion succeeds, returns final directly, skipping astream_events"""
        from app.chat_service import ChatService
        cs = ChatService()
        cs.graph = MagicMock()
        events = [json.loads(e) async for e in cs.stream_events('hello')]
        types = [e['event'] for e in events]
        assert types == ['meta', 'stage', 'final', 'done']
        final = [e for e in events if e['event'] == 'final'][0]
        assert final['data']['content'] == 'Reflexion answer'
        cs.graph.astream_events.assert_not_called()


class TestChatServiceErrors:

    @pytest.mark.asyncio
    @patch('agent.graph.run_agent_with_reflexion', return_value=None)
    async def test_graph_error_emits_error_event(self, _mock_reflexion):
        from app.chat_service import ChatService
        cs = ChatService()
        cs.graph = MagicMock()
        cs.graph.astream_events.side_effect = RuntimeError('Ollama is not running')
        events = [json.loads(e) async for e in cs.stream_events('hello')]
        assert events[0]['event'] == 'meta'
        errors = [e for e in events if e['event'] == 'error']
        assert len(errors) > 0
        assert 'Ollama' in errors[0]['data']['message']

    @pytest.mark.asyncio
    @patch('agent.graph.run_agent_with_reflexion', return_value=None)
    async def test_empty_message_handled(self, _mock_reflexion):
        from app.chat_service import ChatService
        cs = ChatService()
        cs.graph = MagicMock()
        cs.graph.astream_events.return_value = _AsyncIter([])
        events = [json.loads(e) async for e in cs.stream_events('')]
        assert events[0]['event'] == 'meta'
