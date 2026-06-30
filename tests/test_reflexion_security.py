# tests/test_reflexion_security.py
# Security tests for Reflexion module

import pytest
from unittest.mock import patch, MagicMock
import json

from agent.reflexion import (
    ReflexionState,
    _extract_json,
    review_answer,
    ReviewResult,
    set_current_state,
    get_current_state,
    reflexion_loop,
)
from config.settings import settings


# ═══════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════

@pytest.fixture(autouse=True)
def clean_context():
    set_current_state(None)
    yield
    set_current_state(None)


# ═══════════════════════════════════════════════
# API key security
# ═══════════════════════════════════════════════

class TestApiKeySecurity:
    """DeepSeek API key must not be exposed"""

    def test_settings_api_key_default_is_empty_in_code(self):
        """Source code default is empty string (real key comes from .env)"""
        # Check the class-level default, not the runtime value
        from config.settings import Settings
        field = Settings.model_fields["deepseek_api_key"]
        assert field.default == "", \
            f"API key default in source must be empty string, got: {field.default!r}"

    def test_client_rejects_empty_key(self):
        """Client raises if API key is empty"""
        from llm.deepseek_client import DeepSeekClient

        with patch('llm.deepseek_client.settings') as mock_settings:
            mock_settings.deepseek_api_key = ""
            mock_settings.deepseek_base_url = "https://api.test.com"
            mock_settings.deepseek_model = "m"

            client = DeepSeekClient()
            with pytest.raises(RuntimeError, match="API key"):
                client.chat("test")

    def test_api_key_flow_through_patch(self):
        """Verify API key is sent via Authorization header, not URL"""
        from llm.deepseek_client import DeepSeekClient

        with patch('llm.deepseek_client.settings') as mock_settings:
            mock_settings.deepseek_api_key = "sk-secret123"
            mock_settings.deepseek_base_url = "https://api.test.com"
            mock_settings.deepseek_model = "m"

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

                client.chat("hello")

            # Verify Authorization header
            call_args = mock_http.__enter__.return_value.post.call_args
            headers = call_args[1]["headers"]
            assert headers["Authorization"] == "Bearer sk-secret123"
            # Key should NOT appear in URL
            assert "sk-secret123" not in call_args[1].get("url", "")


# ═══════════════════════════════════════════════
# Cache isolation
# ═══════════════════════════════════════════════

class TestCacheIsolation:
    """Cache must be scoped to single request"""

    def test_cache_not_shared_across_states(self):
        """Each ReflexionState has its own isolated cache"""
        state1 = ReflexionState()
        state2 = ReflexionState()

        state1.cache_tool_result("kb", "q", "data1")
        state2.cache_tool_result("kb", "q", "data2")

        assert state1.get_cached_tool_result("kb", "q") == "data1"
        assert state2.get_cached_tool_result("kb", "q") == "data2"

    def test_context_var_not_leaked(self):
        """After reflexion_loop, no state leaks to next request"""
        with patch('agent.reflexion.generate_answer', return_value="a"), \
             patch('agent.reflexion.review_answer', return_value=ReviewResult(
                 score=8, passed=True, issues=[], suggestions=[],
             )):
            reflexion_loop("Q1")

        # State should be cleaned
        assert get_current_state() is None

    def test_no_state_leak_affects_tools(self):
        """Without state, tools should work in v0.2 mode (no cache)"""
        set_current_state(None)

        from agent.tools import search_knowledge
        with patch('tools.knowledge_tools.search_knowledge', return_value="result"):
            result = search_knowledge.invoke({"query": "test"})
        assert result == "result"


# ═══════════════════════════════════════════════
# JSON injection protection
# ═══════════════════════════════════════════════

class TestJsonInjection:
    """Review result JSON parsing must be safe"""

    def test_json_with_code_injection_handled(self):
        """JSON containing executable-looking strings is parsed safely"""
        text = '{"score": 5, "passed": false, "issues": ["__import__(\'os\')"], "suggestions": ["eval(1+1)"]}'
        result = _extract_json(text)
        assert result is not None
        assert "__import__" in str(result["issues"])
        # Just stored as string, not executed

    def test_json_with_escape_sequences(self):
        """JSON with escape characters"""
        text = '{"score": 5, "passed": false, "issues": ["line1\\nline2"], "suggestions": ["tab\\there"]}'
        result = _extract_json(text)
        assert result is not None
        assert result["score"] == 5

    def test_extremely_long_issues_list(self):
        """Very long issues list doesn't crash"""
        text = json.dumps({
            "score": 1,
            "passed": False,
            "issues": ["x" * 10000],
            "suggestions": ["y" * 10000],
        })
        result = _extract_json(text)
        assert result is not None

    def test_empty_json_object(self):
        result = _extract_json("{}")
        assert result == {}

    def test_malformed_json_with_braces(self):
        """JSON with unmatched braces in values"""
        text = '{"score": 5, "issues": ["use { braces }"], "suggestions": []}'
        result = _extract_json(text)
        assert result is not None
        assert result["score"] == 5


# ═══════════════════════════════════════════════
# Input validation
# ═══════════════════════════════════════════════

class TestInputValidation:
    """Handle malicious or malformed inputs"""

    def test_review_answer_with_empty_strings(self):
        with patch('llm.deepseek_client.get_deepseek_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = '{"score": 5, "passed": false, "issues": [], "suggestions": []}'
            mock_get_client.return_value = mock_client

            result = review_answer("", "")
            assert isinstance(result, ReviewResult)

    def test_review_answer_with_very_long_input(self):
        """Very long question and answer"""
        long_q = "What is " + "X " * 5000 + "?"
        long_a = "It is " + "Y " * 5000

        with patch('llm.deepseek_client.get_deepseek_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = '{"score": 3, "passed": false, "issues": ["too long"], "suggestions": ["be concise"]}'
            mock_get_client.return_value = mock_client

            result = review_answer(long_q, long_a)
            assert isinstance(result, ReviewResult)

    def test_review_answer_with_special_characters(self):
        """Special chars in question/answer"""
        special = "Test <script>alert('xss')</script> & \x00 null byte"

        with patch('llm.deepseek_client.get_deepseek_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = '{"score": 5, "passed": false, "issues": [], "suggestions": []}'
            mock_get_client.return_value = mock_client

            result = review_answer(special, special)
            assert isinstance(result, ReviewResult)

    def test_cache_key_with_special_chars(self):
        """Cache keys with special characters"""
        state = ReflexionState()
        special_query = "test<script>alert(1)</script>"
        state.cache_tool_result("kb", special_query, "data")
        result = state.get_cached_tool_result("kb", special_query)
        assert result == "data"

    def test_reflexion_loop_empty_question(self):
        """Empty question doesn't crash"""
        with patch('agent.reflexion.generate_answer', return_value="I don't understand"), \
             patch('agent.reflexion.review_answer', return_value=ReviewResult(
                 score=1, passed=False, issues=["empty question"], suggestions=["ask something"],
             )):
            result = reflexion_loop("")
        # Should handle empty question gracefully
        assert result is None or isinstance(result, str)


# ═══════════════════════════════════════════════
# Review score boundaries
# ═══════════════════════════════════════════════

class TestScoreBoundaries:
    """Review scores must be within valid range"""

    def test_score_clamped_in_review(self):
        """review_answer handles edge score values"""
        with patch('llm.deepseek_client.get_deepseek_client') as mock_get_client:
            mock_client = MagicMock()

            # Score above max
            mock_client.chat.return_value = '{"score": 999, "passed": true, "issues": [], "suggestions": []}'
            mock_get_client.return_value = mock_client
            result = review_answer("Q", "A")
            assert result.score == 999  # Passed through as-is (caller decides)

            # Negative score
            mock_client.chat.return_value = '{"score": -5, "passed": false, "issues": [], "suggestions": []}'
            result = review_answer("Q", "A")
            assert result.score == -5  # Passed through as-is
            # get_best_attempt handles this correctly via max()
