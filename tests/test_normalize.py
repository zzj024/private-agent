# tests/test_normalize.py
# Responsibility: Unit tests for normalize_answer function

import pytest

from agent.graph import normalize_answer


class TestNormalizeAnswer:
    """Test normalize_answer function"""

    def test_empty_string(self):
        """Test: empty string"""
        assert normalize_answer("") == ""
        assert normalize_answer(None) == ""

    def test_normal_text(self):
        """Test: normal text"""
        text = "Hello World"
        assert normalize_answer(text) == "Hello World"

    def test_crlf_to_lf(self):
        """Test: Windows line ending conversion"""
        text = "Hello\r\nWorld"
        assert normalize_answer(text) == "Hello\nWorld"

    def test_trim_whitespace(self):
        """Test: trim whitespace"""
        text = "  Hello World  "
        assert normalize_answer(text) == "Hello World"

    def test_numbered_list_add_blank_line(self):
        """Test: add blank line before numbered list"""
        text = "Answer:\n1. First\n2. Second"
        expected = "Answer:\n\n1. First\n2. Second"
        assert normalize_answer(text) == expected

    def test_chinese_numbered_list(self):
        """Test: Chinese numbered list"""
        text = "Answer:\n1. First\n2. Second"
        expected = "Answer:\n\n1. First\n2. Second"
        assert normalize_answer(text) == expected

    def test_multiple_blank_lines(self):
        """Test: merge multiple blank lines"""
        text = "First paragraph\n\n\n\nSecond paragraph"
        expected = "First paragraph\n\nSecond paragraph"
        assert normalize_answer(text) == expected

    def test_complex_format(self):
        """Test: complex format"""
        text = "  Answer:\r\n1. First\r\n2. Second\r\n\r\n\r\nHope this helps!  "
        expected = "Answer:\n\n1. First\n2. Second\n\nHope this helps!"
        assert normalize_answer(text) == expected
