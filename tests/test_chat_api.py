# tests/test_chat_api.py
# 职责：测试 /chat 和 /chat/stream 端点在 ChatService 改造后的行为

import pytest
import json
from unittest.mock import patch, MagicMock


class _AsyncIter:
    """让普通列表能被 async for 遍历"""
    def __init__(self, items):
        self._items = list(items)
    def __aiter__(self):
        return self
    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


class TestChatEndpoint:
    """测试 POST /chat 的行为"""

    @pytest.fixture
    def mock_chat_service(self):
        with patch("app.main.chat_service") as mock:
            mock.stream_events = MagicMock(return_value=_AsyncIter([
                json.dumps({"event": "meta", "data": {"request_id": "r1", "conversation_id": "42"}}),
                json.dumps({"event": "stage", "data": {"stage": "正在分析...", "message": ""}}),
                json.dumps({"event": "final", "data": {"content": "这是答案", "citations": []}}),
            ]))
            yield mock

    def test_chat_returns_response_json(self, client, mock_chat_service):
        resp = client.post("/chat", json={"message": "你好"})
        assert resp.status_code == 200
        assert resp.json()["response"] == "这是答案"

    def test_chat_with_conversation_id(self, client, mock_chat_service):
        resp = client.post("/chat", json={"message": "你好", "conversation_id": 42})
        assert resp.status_code == 200
        mock_chat_service.stream_events.assert_called_with("你好", conversation_id=42)

    def test_chat_empty_message_returns_200(self, client, mock_chat_service):
        mock_chat_service.stream_events.return_value = _AsyncIter([
            json.dumps({"event": "meta", "data": {}}),
            json.dumps({"event": "final", "data": {"content": "", "citations": []}}),
        ])
        resp = client.post("/chat", json={"message": ""})
        assert resp.status_code == 200
        assert resp.json()["response"] == ""

    def test_chat_error_returns_500(self, client, mock_chat_service):
        mock_chat_service.stream_events.side_effect = RuntimeError("Ollama down")
        resp = client.post("/chat", json={"message": "你好"})
        assert resp.status_code == 500
        assert "Ollama" in resp.json()["detail"]

    def test_chat_no_final_event_returns_none(self, client, mock_chat_service):
        mock_chat_service.stream_events.return_value = _AsyncIter([
            json.dumps({"event": "meta", "data": {}}),
        ])
        resp = client.post("/chat", json={"message": "你好"})
        assert resp.status_code == 200
        assert resp.json()["response"] is None


class TestChatStreamEndpoint:
    """测试 POST /chat/stream 的行为"""

    @pytest.fixture
    def mock_chat_service(self):
        with patch("app.main.chat_service") as mock:
            yield mock

    def test_stream_returns_sse_content_type(self, client, mock_chat_service):
        mock_chat_service.stream_events.return_value = _AsyncIter([
            json.dumps({"event": "meta", "data": {}}),
        ])
        resp = client.post("/chat/stream", json={"message": "你好"})
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    def test_stream_events_forwarded_to_sse(self, client, mock_chat_service):
        mock_chat_service.stream_events.return_value = _AsyncIter([
            json.dumps({"event": "meta", "data": {"request_id": "r1"}}),
            json.dumps({"event": "delta", "data": {"seq": 1, "content": "你"}}),
            json.dumps({"event": "delta", "data": {"seq": 2, "content": "好"}}),
        ])
        resp = client.post("/chat/stream", json={"message": "你好"})
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n\n")
        assert len(lines) == 3
        # 每行以 data: 开头
        for line in resp.text.strip().split("\n\n"):
            assert line.startswith("data: ")
            event = json.loads(line.replace("data: ", ""))
            assert "event" in event

    def test_stream_error_event_included(self, client, mock_chat_service):
        mock_chat_service.stream_events.return_value = _AsyncIter([
            json.dumps({"event": "meta", "data": {}}),
            json.dumps({"event": "error", "data": {
                "code": "AGENT_ERROR", "message": "Something broke", "retryable": True
            }}),
        ])
        resp = client.post("/chat/stream", json={"message": "hi"})
        lines = resp.text.strip().split("\n\n")
        error_event = json.loads(lines[1].replace("data: ", ""))
        assert error_event["event"] == "error"

    def test_stream_with_conversation_id(self, client, mock_chat_service):
        mock_chat_service.stream_events.return_value = _AsyncIter([
            json.dumps({"event": "meta", "data": {}}),
        ])
        resp = client.post("/chat/stream", json={"message": "hi", "conversation_id": 99})
        assert resp.status_code == 200
        mock_chat_service.stream_events.assert_called_with("hi", conversation_id=99)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)