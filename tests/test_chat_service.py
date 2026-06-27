
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
        event_str = cs._make_event('meta', {'request_id': 'abc', 'conversation_id': '123'})
        event = json.loads(event_str)
        assert event['event'] == 'meta'
        assert event['data']['request_id'] == 'abc'

    def test_make_event_unicode_safe(self):
        from app.chat_service import ChatService
        cs = ChatService()
        event_str = cs._make_event('stage', {'stage': '\u6b63\u5728\u5206\u6790\u610f\u56fe...', 'message': '\u5224\u65ad\u4f60\u8981\u505a\u4ec0\u4e48'})
        event = json.loads(event_str)
        assert event['data']['stage'] == '\u6b63\u5728\u5206\u6790\u610f\u56fe...'

    def test_convert_on_chain_start_to_stage(self):
        from app.chat_service import ChatService
        cs = ChatService()
        raw = {'event': 'on_chain_start', 'name': 'detect_intent', 'data': {'input': {'message': '\u4f60\u597d'}}}
        result = cs._convert_langgraph_event(raw)
        event = json.loads(result)
        assert event['event'] == 'stage'
        assert '\u6b63\u5728\u5206\u6790\u610f\u56fe' in event['data']['stage']

    def test_convert_on_chat_model_stream_to_delta(self):
        from app.chat_service import ChatService
        cs = ChatService()
        raw = {'event': 'on_chat_model_stream', 'data': {'chunk': {'content': '\u4f60\u597d'}}}
        result = cs._convert_langgraph_event(raw)
        event = json.loads(result)
        assert event['event'] == 'delta'
        assert event['data']['content'] == '\u4f60\u597d'

    def test_convert_on_chain_end_to_final(self):
        from app.chat_service import ChatService
        cs = ChatService()
        raw = {'event': 'on_chain_end', 'data': {'output': {'response': '\u8fd9\u662f\u6700\u7ec8\u7b54\u6848'}}}
        result = cs._convert_langgraph_event(raw)
        event = json.loads(result)
        assert event['event'] == 'final'
        assert event['data']['content'] == '\u8fd9\u662f\u6700\u7ec8\u7b54\u6848'

    def test_convert_on_chain_error_to_error(self):
        from app.chat_service import ChatService
        cs = ChatService()
        raw = {'event': 'on_chain_error', 'data': {'error': 'Ollama connection refused'}}
        result = cs._convert_langgraph_event(raw)
        event = json.loads(result)
        assert event['event'] == 'error'
        assert 'Ollama' in event['data']['message']
        assert event['data']['retryable'] is True

    def test_unknown_event_returns_empty(self):
        from app.chat_service import ChatService
        cs = ChatService()
        result = cs._convert_langgraph_event({'event': 'on_custom_event', 'data': {}})
        assert result == ''


class TestChatServiceStream:

    @pytest.mark.asyncio
    async def test_stream_emits_meta_first(self):
        from app.chat_service import ChatService
        cs = ChatService()
        cs.graph = MagicMock()
        cs.graph.astream_events.return_value = _AsyncIter([])
        events = [json.loads(e) async for e in cs.stream_events('\u4f60\u597d')]
        assert len(events) > 0
        assert events[0]['event'] == 'meta'

    @pytest.mark.asyncio
    async def test_stream_passes_graph_events_through(self):
        from app.chat_service import ChatService
        mock_events = [
            {'event': 'on_chain_start', 'name': 'detect_intent', 'data': {'input': {}}},
            {'event': 'on_chat_model_stream', 'data': {'chunk': {'content': '\u4f60'}}},
            {'event': 'on_chat_model_stream', 'data': {'chunk': {'content': '\u597d'}}},
            {'event': 'on_chain_end', 'data': {'output': {'response': '\u4f60\u597d\uff01'}}},
        ]
        cs = ChatService()
        cs.graph = MagicMock()
        cs.graph.astream_events.return_value = _AsyncIter(mock_events)
        events = [json.loads(e) async for e in cs.stream_events('\u4f60\u597d')]
        types = [e['event'] for e in events]
        assert types == ['meta', 'stage', 'delta', 'delta', 'final']

    @pytest.mark.asyncio
    async def test_stream_conversation_id_matches(self):
        from app.chat_service import ChatService
        cs = ChatService()
        cs.graph = MagicMock()
        cs.graph.astream_events.return_value = _AsyncIter([])
        events = [json.loads(e) async for e in cs.stream_events('\u4f60\u597d', conversation_id=42)]
        assert events[0]['event'] == 'meta'
        assert events[0]['data']['conversation_id'] == '42'


class TestChatServiceErrors:

    @pytest.mark.asyncio
    async def test_graph_error_emits_error_event(self):
        from app.chat_service import ChatService
        cs = ChatService()
        cs.graph = MagicMock()
        cs.graph.astream_events.side_effect = RuntimeError('Ollama is not running')
        events = [json.loads(e) async for e in cs.stream_events('\u4f60\u597d')]
        assert events[0]['event'] == 'meta'
        errors = [e for e in events if e['event'] == 'error']
        assert len(errors) > 0
        assert 'Ollama' in errors[0]['data']['message']

    @pytest.mark.asyncio
    async def test_empty_message_handled(self):
        from app.chat_service import ChatService
        cs = ChatService()
        cs.graph = MagicMock()
        cs.graph.astream_events.return_value = _AsyncIter([])
        events = [json.loads(e) async for e in cs.stream_events('')]
        assert events[0]['event'] == 'meta'

