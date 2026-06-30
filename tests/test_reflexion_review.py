# tests/test_reflexion_review.py
# Unit tests for review_answer, _extract_json

import pytest
from unittest.mock import patch, MagicMock
import json

from agent.reflexion import (
    review_answer,
    _extract_json,
    ReviewResult,
)


# ═══════════════════════════════════════════════
# _extract_json
# ═══════════════════════════════════════════════

class TestExtractJson:
    """JSON extraction from LLM output"""

    def test_valid_json(self):
        result = _extract_json('{"score": 8, "passed": true, "issues": [], "suggestions": []}')
        assert result == {"score": 8, "passed": True, "issues": [], "suggestions": []}

    def test_json_in_code_block(self):
        text = '```json\n{"score": 7, "passed": true, "issues": ["a"], "suggestions": ["b"]}\n```'
        result = _extract_json(text)
        assert result["score"] == 7
        assert result["passed"] is True

    def test_json_in_code_block_no_lang(self):
        text = '```\n{"score": 6, "passed": false, "issues": ["x"], "suggestions": []}\n```'
        result = _extract_json(text)
        assert result["score"] == 6
        assert result["passed"] is False

    def test_json_with_surrounding_text(self):
        text = 'Here is my review:\n{"score": 9, "passed": true, "issues": [], "suggestions": []}\nHope this helps.'
        result = _extract_json(text)
        assert result["score"] == 9

    def test_invalid_json_returns_none(self):
        result = _extract_json("not json at all")
        assert result is None

    def test_empty_string(self):
        result = _extract_json("")
        assert result is None

    def test_none_input(self):
        result = _extract_json(None)
        assert result is None

    def test_json_with_nested_braces(self):
        """JSON with braces in string values should still parse"""
        text = '{"score": 8, "passed": true, "issues": ["use { and } correctly"], "suggestions": []}'
        result = _extract_json(text)
        assert result["issues"] == ["use { and } correctly"]

    def test_multiple_json_objects_takes_first(self):
        """Extracts the first valid JSON object"""
        text = '{"score": 8, "passed": true}\n{"score": 3, "passed": false}'
        result = _extract_json(text)
        assert result["score"] == 8

    def test_partial_fields_defaulted(self):
        """Missing fields should not crash — caller handles defaults"""
        result = _extract_json('{"score": 5}')
        assert result == {"score": 5}


# ═══════════════════════════════════════════════
# review_answer
# ═══════════════════════════════════════════════

class TestReviewAnswer:
    """Review answer function"""

    def test_review_passed(self):
        mock_response = json.dumps({
            "score": 8,
            "passed": True,
            "issues": [],
            "suggestions": [],
        })

        with patch('llm.deepseek_client.get_deepseek_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = review_answer("What is Redis?", "Redis is KV store")

        assert isinstance(result, ReviewResult)
        assert result.score == 8
        assert result.passed is True

    def test_review_failed_with_feedback(self):
        mock_response = json.dumps({
            "score": 4,
            "passed": False,
            "issues": ["too short", "no code example"],
            "suggestions": ["add code", "explain more"],
        })

        with patch('llm.deepseek_client.get_deepseek_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = review_answer("Q", "A")

        assert result.score == 4
        assert result.passed is False
        assert len(result.issues) == 2
        assert len(result.suggestions) == 2

    def test_review_json_in_code_block(self):
        """DeepSeek wraps JSON in markdown code block"""
        mock_response = '```json\n{"score": 7, "passed": true, "issues": [], "suggestions": []}\n```'

        with patch('llm.deepseek_client.get_deepseek_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = review_answer("Q", "A")

        assert result.score == 7
        assert result.passed is True

    def test_review_unparseable_response(self):
        """When DeepSeek returns unparseable text, return default low score"""
        with patch('llm.deepseek_client.get_deepseek_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = "I cannot evaluate this."
            mock_get_client.return_value = mock_client

            result = review_answer("Q", "A")

        assert result.score == 3
        assert result.passed is False
        assert len(result.issues) > 0

    def test_review_api_exception_returns_default(self):
        """When DeepSeek raises, return default low score"""
        with patch('llm.deepseek_client.get_deepseek_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.side_effect = RuntimeError("Network error")
            mock_get_client.return_value = mock_client

            result = review_answer("Q", "A")

        assert result.score == 3
        assert result.passed is False
        assert "审核服务异常" in str(result.issues)

    def test_review_missing_fields_use_defaults(self):
        """Partial JSON from DeepSeek uses sensible defaults"""
        mock_response = '{"score": 5}'

        with patch('llm.deepseek_client.get_deepseek_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = review_answer("Q", "A")

        assert result.score == 5
        assert result.passed is False
        assert result.issues == []
        assert result.suggestions == []


# ═══════════════════════════════════════════════
# ReviewResult edge cases
# ═══════════════════════════════════════════════

class TestReviewResultEdgeCases:
    """Edge cases for ReviewResult"""

    def test_score_at_boundary(self):
        r = ReviewResult(score=7, passed=True, issues=[], suggestions=[])
        assert r.passed is True
        r2 = ReviewResult(score=6, passed=False, issues=[], suggestions=[])
        assert r2.passed is False

    def test_score_zero_not_negative(self):
        r = ReviewResult(score=0, passed=False, issues=["all wrong"], suggestions=[])
        assert r.score == 0

    def test_max_score(self):
        r = ReviewResult(score=10, passed=True, issues=[], suggestions=[])
        assert r.score == 10

    def test_many_issues(self):
        """Large number of issues"""
        issues = [f"issue_{i}" for i in range(50)]
        suggestions = [f"fix_{i}" for i in range(50)]
        r = ReviewResult(score=2, passed=False, issues=issues, suggestions=suggestions)
        assert len(r.issues) == 50
        assert len(r.suggestions) == 50
