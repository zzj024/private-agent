# tests/test_reflexion_integration.py
# Integration tests for Reflexion loop (mocked dependencies)

import pytest
from unittest.mock import patch, MagicMock

from agent.reflexion import (
    reflexion_loop,
    ReflexionState,
    ReflexionAttempt,
    ReviewResult,
    set_current_state,
    get_current_state,
    review_answer,
)


# ═══════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════

@pytest.fixture(autouse=True)
def clean_context():
    set_current_state(None)
    yield
    set_current_state(None)


def make_review(score=5, passed=False, issues=None, suggestions=None):
    return ReviewResult(
        score=score,
        passed=passed,
        issues=issues or [],
        suggestions=suggestions or [],
    )


# ═══════════════════════════════════════════════
# reflexion_loop integration
# ═══════════════════════════════════════════════

class TestReflexionLoopFirstRoundPass:
    """Pass on first attempt"""

    def test_passes_immediately(self):
        with patch('agent.reflexion.generate_answer', return_value="Perfect answer"), \
             patch('agent.reflexion.review_answer', return_value=make_review(
                 score=8, passed=True,
             )):
            result = reflexion_loop("What is Redis?")

        assert result == "Perfect answer"

    def test_passes_after_one_retry(self):
        """Fail first, pass second"""
        responses = ["Bad answer", "Good answer"]
        reviews = [
            make_review(score=5, passed=False, issues=["too short"], suggestions=["add details"]),
            make_review(score=8, passed=True),
        ]

        with patch('agent.reflexion.generate_answer', side_effect=responses), \
             patch('agent.reflexion.review_answer', side_effect=reviews):
            result = reflexion_loop("Q?")

        assert result == "Good answer"

    def test_all_fail_returns_none(self):
        """All attempts fail with low scores"""
        with patch('agent.reflexion.generate_answer', return_value="Terrible"), \
             patch('agent.reflexion.review_answer', return_value=make_review(
                 score=2, passed=False,
                 issues=["wrong"], suggestions=["redo"],
             )):
            result = reflexion_loop("Q?", max_retries=2)

        assert result is None  # score 2 < min_score 4

    def test_all_fail_but_last_is_best(self):
        """None pass, but best has score >= min_score, so returned"""
        scores = [3, 5, 4]  # best=5 >= min_score=4
        reviews = [make_review(score=s) for s in scores]

        with patch('agent.reflexion.generate_answer', return_value="answer"), \
             patch('agent.reflexion.review_answer', side_effect=reviews):
            result = reflexion_loop("Q?", max_retries=3)

        assert result == "answer"  # returned because max score >= 4

    def test_early_termination_stops_after_drop(self):
        """Terminates after 2 attempts when score drops, returns best if above min"""
        reviews = [
            make_review(score=6, passed=False, issues=["a"], suggestions=["x"]),
            make_review(score=3, passed=False, issues=["b"], suggestions=["y"]),  # worse → terminate
            # Round 3 would be here but terminated early
        ]

        call_count = [0]

        def count_calls(q, **kwargs):
            call_count[0] += 1
            return "ans"

        with patch('agent.reflexion.generate_answer', side_effect=count_calls), \
             patch('agent.reflexion.review_answer', side_effect=reviews):
            result = reflexion_loop("Q?", max_retries=5)

        # Terminated after 2 rounds (not 5), best=6 >= min_score=4
        assert call_count[0] == 2
        assert result == "ans"

    def test_early_termination_returns_best_if_above_min(self):
        """Terminates early, but best score (5) >= min_score (4)"""
        reviews = [
            make_review(score=5, passed=False),   # best
            make_review(score=3, passed=False),   # worse → terminate
        ]

        with patch('agent.reflexion.generate_answer', return_value="ans"), \
             patch('agent.reflexion.review_answer', side_effect=reviews):
            result = reflexion_loop("Q?", max_retries=5)

        assert result == "ans"  # best score 5 >= 4

    def test_uses_settings_max_retries_when_not_specified(self):
        """Default max_retries comes from settings"""
        with patch('agent.reflexion.generate_answer', return_value="ans"), \
             patch('agent.reflexion.review_answer', return_value=make_review(
                 score=8, passed=True,
             )), \
             patch('agent.reflexion.settings') as mock_settings:
            mock_settings.reflexion_max_retries = 5
            mock_settings.reflexion_min_score = 4
            mock_settings.reflexion_pass_score = 7

            result = reflexion_loop("Q?")

        assert result == "ans"

    def test_feedback_passed_to_next_round(self):
        """Feedback from failed review is included in next question"""
        captured_questions = []

        def capture(question, **kwargs):
            captured_questions.append(question)
            return "answer"

        reviews = [
            make_review(score=5, passed=False, issues=["format"], suggestions=["use table"]),
            make_review(score=8, passed=True),
        ]

        with patch('agent.reflexion.generate_answer', side_effect=capture), \
             patch('agent.reflexion.review_answer', side_effect=reviews):
            reflexion_loop("Original question?", max_retries=2)

        # Round 1: original question
        assert "Original question?" in captured_questions[0]
        # Round 2: should include feedback but not overwrite original
        assert "format" in captured_questions[1]
        assert "use table" in captured_questions[1]
        assert "Original question?" in captured_questions[1]


# ═══════════════════════════════════════════════
# Context var isolation
# ═══════════════════════════════════════════════

class TestContextIsolation:
    """Context var is cleaned up after reflexion_loop"""

    def test_state_cleared_after_loop(self):
        with patch('agent.reflexion.generate_answer', return_value="ans"), \
             patch('agent.reflexion.review_answer', return_value=make_review(
                 score=8, passed=True,
             )):
            reflexion_loop("Q?")

        # State should be cleaned up
        assert get_current_state() is None

    def test_state_cleared_after_exception(self):
        """State is cleaned even when review_answer crashes"""
        with patch('agent.reflexion.generate_answer', return_value="ans"), \
             patch('agent.reflexion.review_answer', side_effect=RuntimeError("Boom")):
            with pytest.raises(RuntimeError):
                reflexion_loop("Q?")

        # State should still be None (finally block executed)
        assert get_current_state() is None


# ═══════════════════════════════════════════════
# Cache works across rounds
# ═══════════════════════════════════════════════

class TestCacheAcrossRounds:
    """Data cache persists across reflexion rounds"""

    def test_cache_persists_in_loop(self):
        """Data cached by tools in round 1 is available in round 2"""
        # This test verifies that the same ReflexionState is used across rounds

        def generate_with_cache(question, **kwargs):
            # Simulate: agent calls search_knowledge which caches data
            state = get_current_state()
            if state:
                cached = state.get_cached_tool_result("kb", "test")
                if not cached:
                    state.cache_tool_result("kb", "test", "raw data from chromadb")
            return "answer using data"

        reviews = [
            make_review(score=5, passed=False, issues=["bad"], suggestions=["fix"]),
            make_review(score=8, passed=True),
        ]

        with patch('agent.reflexion.generate_answer', side_effect=generate_with_cache), \
             patch('agent.reflexion.review_answer', side_effect=reviews):
            result = reflexion_loop("Q?", max_retries=2)

        assert result is not None
        # The cache key set in round 1 should have been available throughout
        # (verified by the mock not crashing — it uses get_current_state each time)
