# tests/test_ollama_client.py
# 职责：测试 OllamaClient 的三个核心方法（chat / chat_stream / embed）
# 使用 mock 模拟 HTTP 请求，不依赖 Ollama 是否在运行

import json
import httpx
import pytest
from unittest.mock import patch, MagicMock
from llm.ollama_client import OllamaClient


@pytest.fixture
def client() -> OllamaClient:
    """每个测试用例创建一个新的客户端，指向默认地址"""
    return OllamaClient(base_url="http://127.0.0.1:11434")


# ═══════════════════════════════════════════════
# chat() 测试 —— 普通聊天
# ═══════════════════════════════════════════════

class TestChat:
    """聊天功能的测试"""

    def test_chat_returns_text(self, client: OllamaClient):
        """正常调用 chat() 应该返回模型回答的文本"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": "我是 Qwen，一个 AI 助手。"}
        }

        with patch("httpx.post", return_value=mock_response) as mock_post:
            reply = client.chat("qwen2.5:7b", [
                {"role": "user", "content": "介绍你自己"}
            ])

        assert reply == "我是 Qwen，一个 AI 助手。"
        # 验证发了正确的请求
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://127.0.0.1:11434/api/chat"
        assert kwargs["json"]["model"] == "qwen2.5:7b"
        assert kwargs["json"]["stream"] is False

    def test_chat_with_system_prompt(self, client: OllamaClient):
        """传了 system 参数时，请求体应该包含 system 字段"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": "你是我的私人 Agent。"}
        }

        with patch("httpx.post", return_value=mock_response) as mock_post:
            client.chat(
                "qwen2.5:7b",
                [{"role": "user", "content": "你好"}],
                system="你是一个私人知识库管理员"
            )

        _, kwargs = mock_post.call_args
        assert kwargs["json"]["system"] == "你是一个私人知识库管理员"

    def test_chat_without_system(self, client: OllamaClient):
        """没传 system 时，请求体不应该包含 system 字段"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": "你好！"}}

        with patch("httpx.post", return_value=mock_response) as mock_post:
            client.chat("qwen2.5:7b", [{"role": "user", "content": "hi"}])

        _, kwargs = mock_post.call_args
        assert "system" not in kwargs["json"]

    def test_chat_raises_on_http_error(self, client: OllamaClient):
        """Ollama 返回错误状态码时，应该抛出异常"""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=MagicMock()
        )

        with patch("httpx.post", return_value=mock_response):
            with pytest.raises(httpx.HTTPStatusError):
                client.chat("qwen2.5:7b", [{"role": "user", "content": "hi"}])

    def test_chat_passes_messages_correctly(self, client: OllamaClient):
        """传入的消息列表应该原样传给 Ollama"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": "ok"}}
        messages = [
            {"role": "user", "content": "第一轮"},
            {"role": "assistant", "content": "回答1"},
            {"role": "user", "content": "第二轮"},
        ]

        with patch("httpx.post", return_value=mock_response) as mock_post:
            client.chat("qwen2.5:7b", messages)

        _, kwargs = mock_post.call_args
        assert kwargs["json"]["messages"] == messages

    def test_chat_timeout_is_long(self, client: OllamaClient):
        """聊天超时应该设为 120 秒（模型生成需要时间）"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": "ok"}}

        with patch("httpx.post", return_value=mock_response) as mock_post:
            client.chat("qwen2.5:7b", [{"role": "user", "content": "hi"}])

        _, kwargs = mock_post.call_args
        assert kwargs["timeout"] == 120


# ═══════════════════════════════════════════════
# chat_stream() 测试 —— 流式聊天
# ═══════════════════════════════════════════════

class TestChatStream:
    """流式聊天功能的测试"""

    def test_chat_stream_yields_chunks(self, client: OllamaClient):
        """流式聊天应该逐块 yield 文本"""
        chunks = [
            '{"message":{"content":"你好"},"done":false}\n',
            '{"message":{"content":"，"},"done":false}\n',
            '{"message":{"content":"世界"},"done":false}\n',
            '{"message":{"content":""},"done":true}\n',
        ]

        mock_response = MagicMock()
        mock_response.__enter__.return_value = mock_response
        mock_response.iter_lines.return_value = chunks

        with patch("httpx.stream", return_value=mock_response):
            results = list(client.chat_stream(
                "qwen2.5:7b",
                [{"role": "user", "content": "你好"}]
            ))

        assert results == ["你好", "，", "世界"]

    def test_chat_stream_empty_response(self, client: OllamaClient):
        """模型什么都不返回时，应该得到空列表"""
        chunks = [
            '{"message":{"content":""},"done":true}\n',
        ]

        mock_response = MagicMock()
        mock_response.__enter__.return_value = mock_response
        mock_response.iter_lines.return_value = chunks

        with patch("httpx.stream", return_value=mock_response):
            results = list(client.chat_stream(
                "qwen2.5:7b",
                [{"role": "user", "content": "哦"}]
            ))

        assert results == []

    def test_chat_stream_with_system(self, client: OllamaClient):
        """流式聊天传 system 参数时，请求体应包含 system"""
        chunks = ['{"message":{"content":"ok"},"done":true}\n']

        mock_response = MagicMock()
        mock_response.__enter__.return_value = mock_response
        mock_response.iter_lines.return_value = chunks

        with patch("httpx.stream", return_value=mock_response) as mock_stream:
            list(client.chat_stream(
                "qwen2.5:7b",
                [{"role": "user", "content": "hi"}],
                system="你是一个助手"
            ))

        args, kwargs = mock_stream.call_args
        assert kwargs["json"]["system"] == "你是一个助手"

    def test_chat_stream_raises_on_error(self, client: OllamaClient):
        """流式聊天时 Ollama 报错，应该抛出异常"""
        mock_response = MagicMock()
        mock_response.__enter__.return_value = mock_response
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Server Error", request=MagicMock(), response=MagicMock()
        )

        with patch("httpx.stream", return_value=mock_response):
            with pytest.raises(httpx.HTTPStatusError):
                list(client.chat_stream(
                    "qwen2.5:7b",
                    [{"role": "user", "content": "hi"}]
                ))

    def test_chat_stream_skips_empty_lines(self, client: OllamaClient):
        """流式响应中的空行应该被跳过"""
        chunks = [
            '',   # 空行（空字符串）
            '{"message":{"content":"A"},"done":false}\n',
            '',   # 空行
            '{"message":{"content":"B"},"done":true}\n',
        ]

        mock_response = MagicMock()
        mock_response.__enter__.return_value = mock_response
        mock_response.iter_lines.return_value = chunks

        with patch("httpx.stream", return_value=mock_response):
            results = list(client.chat_stream(
                "qwen2.5:7b",
                [{"role": "user", "content": "test"}]
            ))

        assert results == ["A"]


# ═══════════════════════════════════════════════
# embed() 测试 —— 向量化
# ═══════════════════════════════════════════════

class TestEmbed:
    """Embedding 功能的测试"""

    def test_embed_returns_vector(self, client: OllamaClient):
        """正常调用 embed() 应该返回一个浮点数列表"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "embeddings": [[0.123, -0.456, 0.789]]
        }

        with patch("httpx.post", return_value=mock_response) as mock_post:
            vector = client.embed("nomic-embed-text", "Hello world")

        assert isinstance(vector, list)
        assert len(vector) == 3
        assert vector == [0.123, -0.456, 0.789]

        # 验证请求地址和参数（v0.5: embed 内部调用 embed_batch，input 变为数组）
        args, kwargs = mock_post.call_args
        assert args[0] == "http://127.0.0.1:11434/api/embed"
        assert kwargs["json"]["model"] == "nomic-embed-text"
        assert kwargs["json"]["input"] == ["Hello world"]

    def test_embed_cjk_text(self, client: OllamaClient):
        """中文字符应该能正常向量化"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "embeddings": [[0.1, 0.2]]
        }

        with patch("httpx.post", return_value=mock_response):
            vector = client.embed("nomic-embed-text", "你好世界")

        assert len(vector) == 2

    def test_embed_timeout(self, client: OllamaClient):
        """v0.5: batch embedding 超时设为 300 秒"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"embeddings": [[0.1]]}

        with patch("httpx.post", return_value=mock_response) as mock_post:
            client.embed("nomic-embed-text", "test")

        _, kwargs = mock_post.call_args
        assert kwargs["timeout"] == 300


# ═══════════════════════════════════════════════
# 边界情况测试
# ═══════════════════════════════════════════════

class TestEdgeCases:
    """边界和异常情况测试"""

    def test_base_url_strips_trailing_slash(self):
        """初始化时 base_url 末尾的斜杠应该被去掉"""
        client = OllamaClient(base_url="http://127.0.0.1:11434/")
        assert client.base_url == "http://127.0.0.1:11434"

    def test_base_url_without_slash(self):
        """base_url 末尾没有斜杠时保持不变"""
        client = OllamaClient(base_url="http://127.0.0.1:11434")
        assert client.base_url == "http://127.0.0.1:11434"

    def test_chat_connection_error(self, client: OllamaClient):
        """Ollama 没有在运行时，应该抛出连接错误"""
        with patch("httpx.post", side_effect=httpx.ConnectError(
            "Connection refused"
        )):
            with pytest.raises(httpx.ConnectError):
                client.chat("qwen2.5:7b", [{"role": "user", "content": "hi"}])

    def test_chat_timeout_error(self, client: OllamaClient):
        """请求超时时应该抛出 TimeoutException"""
        with patch("httpx.post", side_effect=httpx.TimeoutException(
            "Request timed out"
        )):
            with pytest.raises(httpx.TimeoutException):
                client.chat("qwen2.5:7b", [{"role": "user", "content": "hi"}])

    def test_empty_messages_list(self, client: OllamaClient):
        """空的 messages 列表也应该能正常发送"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": ""}}

        with patch("httpx.post", return_value=mock_response):
            reply = client.chat("qwen2.5:7b", [])

        assert reply == ""

    def test_multiple_conversation_turns(self, client: OllamaClient):
        """多轮对话的消息历史应该完整传递"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": "我明白了"}}

        history = [
            {"role": "user", "content": "我的技术栈是 Java"},
            {"role": "assistant", "content": "好的，已记录"},
            {"role": "user", "content": "帮我总结一下"},
        ]

        with patch("httpx.post", return_value=mock_response) as mock_post:
            client.chat("qwen2.5:7b", history)

        _, kwargs = mock_post.call_args
        assert len(kwargs["json"]["messages"]) == 3
        assert kwargs["json"]["messages"][0]["content"] == "我的技术栈是 Java"


# ═══════════════════════════════════════════════
# get_ollama_client() 测试
# ═══════════════════════════════════════════════

class TestGetClient:
    """快捷函数 get_ollama_client 的测试"""

    def test_get_ollama_client_returns_instance(self):
        """get_ollama_client 应该返回一个 OllamaClient 实例"""
        from llm.ollama_client import get_ollama_client
        client = get_ollama_client()
        assert isinstance(client, OllamaClient)
        assert client.base_url is not None
