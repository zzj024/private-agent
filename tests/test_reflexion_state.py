# tests/test_reflexion_state.py
# Unit tests for ReflexionState data structure

import pytest
from dataclasses import dataclass
from typing import List


# Import directly (no langchain_ollama dependency)
from agent.reflexion import (
    ReflexionState,
    ReflexionAttempt,
    ReviewResult,
    set_current_state,
    get_current_state,
)


# ═══════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════

def make_review(score=5, passed=False, issues=None, suggestions=None):
    return ReviewResult(
        score=score,
        passed=passed,
        issues=issues or [],
        suggestions=suggestions or [],
    )


def make_attempt(attempt=1, answer="test answer", review=None):
    return ReflexionAttempt(
        attempt=attempt,
        answer=answer,
        review=review or make_review(),
        cached_data={},
    )


# ═══════════════════════════════════════════════
# ReviewResult
# ═══════════════════════════════════════════════

class TestReviewResult:
    """ReviewResult dataclass"""

    def test_create_with_all_fields(self):
        r = ReviewResult(
            score=8,
            passed=True,
            issues=["format error"],
            suggestions=["use markdown table"],
        )
        assert r.score == 8
        assert r.passed is True
        assert r.issues == ["format error"]
        assert r.suggestions == ["use markdown table"]

    def test_create_with_empty_lists(self):
        r = ReviewResult(score=10, passed=True, issues=[], suggestions=[])
        assert r.score == 10
        assert r.issues == []

    def test_score_zero(self):
        r = ReviewResult(score=0, passed=False, issues=["total failure"], suggestions=[])
        assert r.score == 0
        assert r.passed is False


# ═══════════════════════════════════════════════
# ReflexionAttempt
# ═══════════════════════════════════════════════

class TestReflexionAttempt:
    """ReflexionAttempt dataclass"""

    def test_create_attempt(self):
        review = make_review(score=7, passed=True)
        a = ReflexionAttempt(attempt=1, answer="hello", review=review, cached_data={"kb:test": "data"})
        assert a.attempt == 1
        assert a.answer == "hello"
        assert a.review.score == 7
        assert a.cached_data == {"kb:test": "data"}

    def test_cached_data_stored_correctly(self):
        """cached_data is stored as provided (caller does .copy())"""
        cache = {"kb:a": "1"}
        review = make_review()
        a = ReflexionAttempt(attempt=1, answer="test", review=review, cached_data=cache)
        assert a.cached_data == {"kb:a": "1"}


# ═══════════════════════════════════════════════
# ReflexionState - cache
# ═══════════════════════════════════════════════

class TestReflexionStateCache:
    """Tool-layer data cache"""

    def test_cache_and_get_tool_result(self):
        state = ReflexionState()
        state.cache_tool_result("kb", "redis config", "chunk1, chunk2")
        assert state.get_cached_tool_result("kb", "redis config") == "chunk1, chunk2"

    def test_cache_key_normalization(self):
        """Query normalization: whitespace and case are normalized"""
        state = ReflexionState()
        state.cache_tool_result("kb", "  Redis  CONFIG  ", "data")
        assert state.get_cached_tool_result("kb", "redis config") == "data"
        assert state.get_cached_tool_result("kb", "REDIS CONFIG") == "data"

    def test_cache_miss_returns_none(self):
        state = ReflexionState()
        assert state.get_cached_tool_result("kb", "nonexistent") is None

    def test_cache_empty_state(self):
        state = ReflexionState()
        assert state.get_cached_tool_result("kb", "anything") is None

    def test_cache_multiple_tools(self):
        """Different tool names don't collide"""
        state = ReflexionState()
        state.cache_tool_result("kb", "query", "kb_data")
        state.cache_tool_result("memory", "query", "mem_data")
        assert state.get_cached_tool_result("kb", "query") == "kb_data"
        assert state.get_cached_tool_result("memory", "query") == "mem_data"

    def test_cache_overwrite(self):
        """Same key overwrites previous value"""
        state = ReflexionState()
        state.cache_tool_result("kb", "query", "v1")
        state.cache_tool_result("kb", "query", "v2")
        assert state.get_cached_tool_result("kb", "query") == "v2"

    def test_clear_all_cache(self):
        state = ReflexionState()
        state.cache_tool_result("kb", "a", "1")
        state.cache_tool_result("memory", "b", "2")
        state.clear_cache()
        assert state.get_cached_tool_result("kb", "a") is None
        assert state.get_cached_tool_result("memory", "b") is None

    def test_clear_cache_by_prefix(self):
        state = ReflexionState()
        state.cache_tool_result("kb", "a", "1")
        state.cache_tool_result("memory", "b", "2")
        state.clear_cache("memory:")
        assert state.get_cached_tool_result("kb", "a") == "1"  # kb untouched
        assert state.get_cached_tool_result("memory", "b") is None  # memory cleared

    def test_clear_cache_non_matching_prefix(self):
        """Prefix that doesn't match keeps everything"""
        state = ReflexionState()
        state.cache_tool_result("kb", "a", "1")
        state.clear_cache("nonexistent:")
        assert state.get_cached_tool_result("kb", "a") == "1"

    def test_normalize_key_removes_unicode_whitespace(self):
        state = ReflexionState()
        # Full-width spaces and tabs
        key = state._normalize_key("　 redis \t config 　")
        assert key == "redis config"


# ═══════════════════════════════════════════════
# ReflexionState - attempts
# ═══════════════════════════════════════════════

class TestReflexionStateAttempts:
    """Managing reflexion attempts"""

    def test_add_and_get_best(self):
        state = ReflexionState()
        state.add_attempt(make_attempt(1, "a", make_review(score=5)))
        state.add_attempt(make_attempt(2, "b", make_review(score=8)))
        state.add_attempt(make_attempt(3, "c", make_review(score=6)))
        best = state.get_best_attempt()
        assert best.answer == "b"
        assert best.review.score == 8

    def test_get_best_empty(self):
        state = ReflexionState()
        assert state.get_best_attempt() is None

    def test_get_best_single_attempt(self):
        state = ReflexionState()
        state.add_attempt(make_attempt(1, "only", make_review(score=3)))
        best = state.get_best_attempt()
        assert best.answer == "only"
        assert best.review.score == 3  # returns even low score

    def test_get_best_same_score_returns_first(self):
        """When scores are equal, max() returns first due to stable sort"""
        state = ReflexionState()
        state.add_attempt(make_attempt(1, "first", make_review(score=5)))
        state.add_attempt(make_attempt(2, "second", make_review(score=5)))
        best = state.get_best_attempt()
        # max() on tuples is stable, but for same score either is valid
        assert best.review.score == 5
        assert best.answer in ("first", "second")

    def test_attempts_order_preserved(self):
        state = ReflexionState()
        for i in range(5):
            state.add_attempt(make_attempt(i + 1, f"a{i}", make_review(score=i)))
        assert len(state.attempts) == 5
        assert state.attempts[0].attempt == 1
        assert state.attempts[-1].attempt == 5


# ═══════════════════════════════════════════════
# ReflexionState - early termination
# ═══════════════════════════════════════════════

class TestShouldTerminateEarly:
    """Early termination logic"""

    def test_false_when_less_than_2_attempts(self):
        state = ReflexionState()
        assert state.should_terminate_early() is False
        state.add_attempt(make_attempt(1, "a", make_review(score=5)))
        assert state.should_terminate_early() is False

    def test_true_when_score_decreases(self):
        state = ReflexionState()
        state.add_attempt(make_attempt(1, "a", make_review(score=7)))
        state.add_attempt(make_attempt(2, "b", make_review(score=5)))
        assert state.should_terminate_early() is True

    def test_true_when_score_stays_same(self):
        state = ReflexionState()
        state.add_attempt(make_attempt(1, "a", make_review(score=5)))
        state.add_attempt(make_attempt(2, "b", make_review(score=5)))
        assert state.should_terminate_early() is True

    def test_false_when_score_improves(self):
        state = ReflexionState()
        state.add_attempt(make_attempt(1, "a", make_review(score=5)))
        state.add_attempt(make_attempt(2, "b", make_review(score=8)))
        assert state.should_terminate_early() is False

    def test_only_checks_last_two(self):
        """Only compares last two, ignores older history"""
        state = ReflexionState()
        state.add_attempt(make_attempt(1, "a", make_review(score=10)))
        state.add_attempt(make_attempt(2, "b", make_review(score=3)))   # dropped
        state.add_attempt(make_attempt(3, "c", make_review(score=8)))   # improved from 3
        assert state.should_terminate_early() is False


# ═══════════════════════════════════════════════
# Context variable
# ═══════════════════════════════════════════════

class TestContextVar:
    """Context variable for passing state to tools"""

    def test_set_and_get(self):
        state = ReflexionState()
        set_current_state(state)
        assert get_current_state() is state

    def test_default_is_none(self):
        # Reset to ensure clean state
        set_current_state(None)
        assert get_current_state() is None

    def test_set_none_clears(self):
        state = ReflexionState()
        set_current_state(state)
        set_current_state(None)
        assert get_current_state() is None


# ═══════════════════════════════════════════════
# ReflexionState - complete flow simulation
# ═══════════════════════════════════════════════

class TestReflexionStateFullFlow:
    """Simulate a complete Reflexion cycle pattern"""

    def test_typical_reflexion_flow(self):
        """Simulate: round1 fail → round2 improve → pass"""
        state = ReflexionState()
        state.question = "What is Redis?"

        # Round 1: LLM queries KB, gets raw data cached
        state.cache_tool_result("kb", "redis", "[chunk1] Redis is KV store")
        state.add_attempt(make_attempt(1, "Redis is a database", make_review(
            score=5, passed=False,
            issues=["too vague"], suggestions=["mention KV store"],
        )))

        # Check cache persist across rounds
        assert state.get_cached_tool_result("kb", "redis") == "[chunk1] Redis is KV store"

        # Round 2: improved answer with cached data still available
        state.add_attempt(make_attempt(2, "Redis is an in-memory KV store", make_review(
            score=8, passed=True,
        )))

        # Should not terminate early (score improved)
        assert state.should_terminate_early() is False

        # Best should be round 2
        best = state.get_best_attempt()
        assert best.attempt == 2
        assert best.review.score == 8

    def test_cache_persists_across_rounds(self):
        """Data cached in round 1 is still available in round 2+"""
        state = ReflexionState()
        state.cache_tool_result("kb", "topic", "raw_data")

        # Round 1
        state.add_attempt(make_attempt(1, "ans1", make_review(
            score=5, passed=False, issues=["bad"], suggestions=["fix"],
        )))

        # Round 2 — cache still there
        assert state.get_cached_tool_result("kb", "topic") == "raw_data"

    def test_clear_cache_after_write_operation(self):
        """After save_memory, memory cache should be cleared"""
        state = ReflexionState()
        state.cache_tool_result("memory", "list_all", "[mem1, mem2]")
        state.cache_tool_result("kb", "query", "[chunk]")

        # Simulate delete_memory clearing memory cache
        state.clear_cache("memory:")

        assert state.get_cached_tool_result("memory", "list_all") is None
        assert state.get_cached_tool_result("kb", "query") == "[chunk]"  # kb untouched
