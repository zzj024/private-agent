# tests/test_deepseek_client.py
# Unit tests for DeepSeekClient

import pytest
from unittest.mock import patch, MagicMock
import httpx

from llm.deepseek_client import DeepSeekClient, get_deepseek_client


# ═══════════════════════════════════════════════
# DeepSeekClient
# ═══════════════════════════════════════════════

class TestDeepSeekClientInit:
    """Client initialization"""

    def test_init_reads_settings(self):
        with patch('llm.deepseek_client.settings') as mock_settings:
            mock_settings.deepseek_base_url = 'https://api.test.com'
            mock_settings.deepseek_api_key = 'sk-test'
            mock_settings.deepseek_model = 'deepseek-test'

            client = DeepSeekClient()
            assert client.base_url == 'https://api.test.com'
            assert client.api_key == 'sk-test'
            assert client.model == 'deepseek-test'

    def test_init_strips_trailing_slash(self):
        with patch('llm.deepseek_client.settings') as mock_settings:
            mock_settings.deepseek_base_url = 'https://api.test.com/'
            mock_settings.deepseek_api_key = 'sk'
            mock_settings.deepseek_model = 'm'

            client = DeepSeekClient()
            assert client.base_url == 'https://api.test.com'

    def test_chat_no_api_key_raises(self):
        with patch('llm.deepseek_client.settings') as mock_settings:
            mock_settings.deepseek_api_key = ''
            mock_settings.deepseek_base_url = 'https://api.test.com'
            mock_settings.deepseek_model = 'm'

            client = DeepSeekClient()
            with pytest.raises(RuntimeError, match="API key"):
                client.chat("hello")


class TestDeepSeekClientChat:
    """Chat method with mocked HTTP"""

    def test_chat_success(self):
        with patch('llm.deepseek_client.settings') as mock_settings:
            mock_settings.deepseek_api_key = 'sk-test'
            mock_settings.deepseek_base_url = 'https://api.test.com'
            mock_settings.deepseek_model = 'deepseek-test'

            client = DeepSeekClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Hello world"}}]
            }
            mock_response.raise_for_status = MagicMock()

            with patch('httpx.Client') as mock_client_class:
                mock_http = MagicMock()
                mock_http.__enter__.return_value.post.return_value = mock_response
                mock_client_class.return_value = mock_http

                result = client.chat("prompt")
                assert result == "Hello world"

    def test_chat_with_system_prompt(self):
        with patch('llm.deepseek_client.settings') as mock_settings:
            mock_settings.deepseek_api_key = 'sk-test'
            mock_settings.deepseek_base_url = 'https://api.test.com'
            mock_settings.deepseek_model = 'm'

            client = DeepSeekClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "ok"}}]
            }
            mock_response.raise_for_status = MagicMock()

            with patch('httpx.Client') as mock_client_class:
                mock_http = MagicMock()
                mock_http.__enter__.return_value.post.return_value = mock_response
                mock_client_class.return_value = mock_http

                result = client.chat("prompt", system="You are helpful")
                assert result == "ok"

    def test_chat_401_unauthorized(self):
        with patch('llm.deepseek_client.settings') as mock_settings:
            mock_settings.deepseek_api_key = 'sk-bad'
            mock_settings.deepseek_base_url = 'https://api.test.com'
            mock_settings.deepseek_model = 'm'

            client = DeepSeekClient()

            with patch('httpx.Client') as mock_client_class:
                error_response = MagicMock()
                error_response.status_code = 401
                error_response.text = 'Unauthorized'

                mock_http = MagicMock()
                mock_http.__enter__.return_value.post.side_effect = \
                    httpx.HTTPStatusError("401", request=MagicMock(), response=error_response)
                mock_client_class.return_value = mock_http

                with pytest.raises(RuntimeError, match="API key"):
                    client.chat("prompt")

    def test_chat_429_rate_limit(self):
        with patch('llm.deepseek_client.settings') as mock_settings:
            mock_settings.deepseek_api_key = 'sk-good'
            mock_settings.deepseek_base_url = 'https://api.test.com'
            mock_settings.deepseek_model = 'm'

            client = DeepSeekClient()

            with patch('httpx.Client') as mock_client_class:
                error_response = MagicMock()
                error_response.status_code = 429
                error_response.text = 'Rate limited'

                mock_http = MagicMock()
                mock_http.__enter__.return_value.post.side_effect = \
                    httpx.HTTPStatusError("429", request=MagicMock(), response=error_response)
                mock_client_class.return_value = mock_http

                with pytest.raises(RuntimeError, match="频率超限"):
                    client.chat("prompt")

    def test_chat_500_server_error(self):
        with patch('llm.deepseek_client.settings') as mock_settings:
            mock_settings.deepseek_api_key = 'sk'
            mock_settings.deepseek_base_url = 'https://api.test.com'
            mock_settings.deepseek_model = 'm'

            client = DeepSeekClient()

            with patch('httpx.Client') as mock_client_class:
                error_response = MagicMock()
                error_response.status_code = 500
                error_response.text = 'Internal error'

                mock_http = MagicMock()
                mock_http.__enter__.return_value.post.side_effect = \
                    httpx.HTTPStatusError("500", request=MagicMock(), response=error_response)
                mock_client_class.return_value = mock_http

                with pytest.raises(RuntimeError, match="服务异常"):
                    client.chat("prompt")

    def test_chat_timeout(self):
        with patch('llm.deepseek_client.settings') as mock_settings:
            mock_settings.deepseek_api_key = 'sk'
            mock_settings.deepseek_base_url = 'https://api.test.com'
            mock_settings.deepseek_model = 'm'

            client = DeepSeekClient()

            with patch('httpx.Client') as mock_client_class:
                mock_http = MagicMock()
                mock_http.__enter__.return_value.post.side_effect = httpx.TimeoutException("timeout")
                mock_client_class.return_value = mock_http

                with pytest.raises(RuntimeError, match="超时"):
                    client.chat("prompt")

    def test_chat_network_error(self):
        with patch('llm.deepseek_client.settings') as mock_settings:
            mock_settings.deepseek_api_key = 'sk'
            mock_settings.deepseek_base_url = 'https://api.test.com'
            mock_settings.deepseek_model = 'm'

            client = DeepSeekClient()

            with patch('httpx.Client') as mock_client_class:
                mock_http = MagicMock()
                mock_http.__enter__.return_value.post.side_effect = \
                    httpx.RequestError("DNS failure")
                mock_client_class.return_value = mock_http

                with pytest.raises(RuntimeError, match="网络连接"):
                    client.chat("prompt")

    def test_chat_403_forbidden(self):
        with patch('llm.deepseek_client.settings') as mock_settings:
            mock_settings.deepseek_api_key = 'sk'
            mock_settings.deepseek_base_url = 'https://api.test.com'
            mock_settings.deepseek_model = 'm'

            client = DeepSeekClient()

            with patch('httpx.Client') as mock_client_class:
                error_response = MagicMock()
                error_response.status_code = 403
                error_response.text = 'Forbidden'

                mock_http = MagicMock()
                mock_http.__enter__.return_value.post.side_effect = \
                    httpx.HTTPStatusError("403", request=MagicMock(), response=error_response)
                mock_client_class.return_value = mock_http

                with pytest.raises(RuntimeError, match="请求失败"):
                    client.chat("prompt")


# ═══════════════════════════════════════════════
# Singleton get_deepseek_client
# ═══════════════════════════════════════════════

class TestGetDeepSeekClient:
    """Singleton factory function"""

    def test_returns_deepseek_client(self):
        with patch('llm.deepseek_client.settings') as mock_settings:
            mock_settings.deepseek_api_key = ''
            mock_settings.deepseek_base_url = 'https://api.test.com'
            mock_settings.deepseek_model = 'm'

            # Reset singleton
            import llm.deepseek_client as dsc
            dsc._client = None

            client = get_deepseek_client()
            assert isinstance(client, DeepSeekClient)

    def test_singleton_returns_same_instance(self):
        with patch('llm.deepseek_client.settings') as mock_settings:
            mock_settings.deepseek_api_key = ''
            mock_settings.deepseek_base_url = 'https://api.test.com'
            mock_settings.deepseek_model = 'm'

            import llm.deepseek_client as dsc
            dsc._client = None

            c1 = get_deepseek_client()
            c2 = get_deepseek_client()
            assert c1 is c2
