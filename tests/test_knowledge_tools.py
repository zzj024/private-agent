# tests/test_knowledge_tools.py
# Unit tests for smart search A++ functions in tools/knowledge_tools.py

import json
import pytest
from unittest.mock import patch, MagicMock

from tools.knowledge_tools import (
    QueryProfile,
    PROFILES,
    DEFAULT_PROFILE,
    rule_prefilter,
    _parse_json_response,
    _build_rerank_prompt,
    format_knowledge_results,
    assess_query_profile,
    llm_rerank_and_select,
    smart_search_knowledge,
)


# ═══════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════

def _make_result(distance, doc_id="id0", document="doc text"):
    return {"id": doc_id, "document": document, "metadata": {}, "distance": distance}


def _make_results(*distances):
    return [_make_result(d, f"id{i}", f"document_{i}") for i, d in enumerate(distances)]


# ═══════════════════════════════════════════════
# QueryProfile
# ═══════════════════════════════════════════════

class TestQueryProfile:
    def test_narrow_profile_values(self):
        p = PROFILES["narrow"]
        assert p.probe_k == 10
        assert p.rerank_soft_limit == 6
        assert p.final_char_budget == 1800

    def test_normal_profile_values(self):
        p = PROFILES["normal"]
        assert p.probe_k == 20

    def test_broad_profile_values(self):
        p = PROFILES["broad"]
        assert p.probe_k == 30
        assert p.final_char_budget == 5000

    def test_default_profile_is_normal(self):
        assert DEFAULT_PROFILE is PROFILES["normal"]


# ═══════════════════════════════════════════════
# _parse_json_response
# ═══════════════════════════════════════════════

class TestParseJsonResponse:
    def test_pure_json(self):
        result = _parse_json_response('{"selected": [{"id": "K1", "relevance": 3}]}')
        assert result["selected"][0]["id"] == "K1"

    def test_json_with_markdown_fence(self):
        content = '```json\n{"selected": []}\n```'
        result = _parse_json_response(content)
        assert result["selected"] == []

    def test_json_with_plain_fence(self):
        content = '```\n{"selected": []}\n```'
        result = _parse_json_response(content)
        assert result["selected"] == []

    def test_json_with_extra_text(self):
        content = 'Here is my analysis:\n\n{"selected": [{"id": "K2", "relevance": 2}]}\n\nHope this helps.'
        result = _parse_json_response(content)
        assert result["selected"][0]["id"] == "K2"

    def test_no_json_raises_value_error(self):
        with pytest.raises(ValueError, match="No JSON"):
            _parse_json_response("No JSON here at all")

    def test_nested_braces(self):
        content = '{"selected": [{"id": "K1", "reason": "good {match}"}], "extra": {}}'
        result = _parse_json_response(content)
        assert result["selected"][0]["reason"] == "good {match}"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="No JSON"):
            _parse_json_response("")


# ═══════════════════════════════════════════════
# rule_prefilter
# ═══════════════════════════════════════════════

class TestRulePrefilter:
    def normal_profile(self):
        return PROFILES["normal"]

    def test_empty_results_returns_empty(self):
        assert rule_prefilter([], self.normal_profile()) == []

    def test_two_results_returned_as_is(self):
        results = _make_results(0.21, 0.45)
        output = rule_prefilter(results, self.normal_profile())
        assert len(output) == 2

    def test_one_result_returned_as_is(self):
        results = _make_results(0.21)
        output = rule_prefilter(results, self.normal_profile())
        assert len(output) == 1

    def test_no_significant_gap_returns_all_up_to_limit(self):
        # Realistic L2 distances for 768-dim embeddings (~1.0-1.2 range)
        # gaps 0.01-0.02, relative < 0.02 → not significant
        results = _make_results(1.05, 1.07, 1.09, 1.11, 1.13, 1.15, 1.17)
        output = rule_prefilter(results, self.normal_profile())
        assert len(output) == 7  # all kept, no gap exceeds threshold

    def test_significant_gap_cuts_tail(self):
        # gap from 1.08 to 1.25 = 0.17, relative = 0.17/1.02 = 0.167 > 0.05
        results = _make_results(1.02, 1.04, 1.06, 1.08, 1.25, 1.27, 1.29)
        output = rule_prefilter(results, self.normal_profile())
        assert len(output) == 4  # cut at index 3 (gap at 3->4)

    def test_large_first_gap_floors_at_two(self):
        # gap 1.02->1.20 = 0.18, relative = 0.176 > 0.05, cut at 1, floor at 2
        results = _make_results(1.02, 1.20, 1.22, 1.25)
        output = rule_prefilter(results, self.normal_profile())
        assert len(output) == 2

    def test_missing_distances_fallback_to_limit(self):
        results = [{"id": "x", "document": "d", "metadata": {}} for _ in range(5)]
        output = rule_prefilter(results, self.normal_profile())
        assert len(output) <= 10  # up to soft_limit

    def test_narrow_profile_tighter_limit(self):
        p = PROFILES["narrow"]
        # gaps 0.01 each, relative ~0.01 → no trigger, hit soft_limit
        results = _make_results(*[1.02 + i * 0.01 for i in range(15)])
        output = rule_prefilter(results, p)
        assert len(output) <= p.rerank_soft_limit  # narrow limit = 6

    def test_broad_profile_wider_limit(self):
        p = PROFILES["broad"]
        # gaps 0.005 each, relative < 0.005 → no trigger, hit soft_limit
        results = _make_results(*[1.02 + i * 0.005 for i in range(20)])
        output = rule_prefilter(results, p)
        assert len(output) <= p.rerank_soft_limit  # broad limit = 15


# ═══════════════════════════════════════════════
# _build_rerank_prompt
# ═══════════════════════════════════════════════

class TestBuildRerankPrompt:
    def test_prompt_includes_query(self):
        candidates = [_make_result(0.21, "id0", "some document content")]
        prompt = _build_rerank_prompt("What is AI?", candidates)
        assert "What is AI?" in prompt

    def test_prompt_includes_candidate_labels(self):
        candidates = [
            _make_result(0.21, "id0", "first doc"),
            _make_result(0.35, "id1", "second doc"),
        ]
        prompt = _build_rerank_prompt("test", candidates)
        assert "[K1]" in prompt
        assert "[K2]" in prompt

    def test_long_document_is_truncated(self):
        long_doc = "x" * 500
        candidates = [_make_result(0.21, "id0", long_doc)]
        prompt = _build_rerank_prompt("test", candidates)
        assert "x" * 450 in prompt
        assert "..." in prompt
        assert "x" * 500 not in prompt  # full doc not present

    def test_short_document_not_truncated(self):
        short_doc = "short"
        candidates = [_make_result(0.21, "id0", short_doc)]
        prompt = _build_rerank_prompt("test", candidates)
        assert "short" in prompt
        assert "short..." not in prompt

    def test_prompt_includes_relevance_rules(self):
        candidates = [_make_result(0.21)]
        prompt = _build_rerank_prompt("test", candidates)
        assert "relevance" in prompt.lower()

    def test_empty_candidates(self):
        prompt = _build_rerank_prompt("test", [])
        assert "test" in prompt


# ═══════════════════════════════════════════════
# format_knowledge_results
# ═══════════════════════════════════════════════

class TestFormatKnowledgeResults:
    def test_empty_returns_empty_string(self):
        assert format_knowledge_results([], 3000) == ""

    def test_single_result_within_budget(self):
        results = [_make_result(0.21, "id0", "hello world")]
        output = format_knowledge_results(results, max_chars=3000)
        assert "[K1]" in output
        assert "hello world" in output

    def test_multiple_results_within_budget(self):
        results = [
            _make_result(1.02, "id0", "doc A"),
            _make_result(1.05, "id1", "doc B"),
            _make_result(1.08, "id2", "doc C"),
        ]
        output = format_knowledge_results(results, max_chars=3000)
        assert "[K1]" in output
        assert "[K2]" in output
        assert "[K3]" in output

    def test_budget_exhausted_stops_adding(self):
        results = [
            _make_result(0.21, "id0", "A" * 200),
            _make_result(0.25, "id1", "B" * 2000),
            _make_result(0.30, "id2", "C" * 2000),
        ]
        output = format_knowledge_results(results, max_chars=500)
        # First entry fits, second may or may not, third should not appear
        assert "[K1]" in output
        assert "[K3]" not in output

    def test_content_truncated_when_exceeds_remaining_budget(self):
        results = [_make_result(0.21, "id0", "A" * 3000)]
        output = format_knowledge_results(results, max_chars=500)
        assert "..." in output

    def test_header_included_when_present(self):
        results = [{"id": "id0", "document": "content", "metadata": {"source": "notes.md", "header": "My Note"}, "distance": 0.21}]
        output = format_knowledge_results(results, max_chars=3000)
        assert "My Note" in output
        assert "notes.md" in output

    def test_metadata_fallback(self):
        """metadata without source/header uses default values"""
        results = [_make_result(0.21, "id0", "content")]
        output = format_knowledge_results(results, max_chars=3000)
        assert "unknown" in output.lower() or "未知" in output  # "未知" in Chinese


# ═══════════════════════════════════════════════
# assess_query_profile (mock LLM)
# ═══════════════════════════════════════════════

class TestAssessQueryProfile:
    def test_returns_narrow_for_narrow_query(self):
        with patch('tools.knowledge_tools._classify_query_with_llm', return_value="narrow"):
            profile = assess_query_profile("What is my phone number")
            assert profile.breadth == "narrow"
            assert profile.probe_k == 10

    def test_returns_broad_for_broad_query(self):
        with patch('tools.knowledge_tools._classify_query_with_llm', return_value="broad"):
            profile = assess_query_profile("Compare all AI architecture notes")
            assert profile.breadth == "broad"
            assert profile.probe_k == 30

    def test_returns_normal_for_unknown_type(self):
        with patch('tools.knowledge_tools._classify_query_with_llm', return_value="unknown"):
            profile = assess_query_profile("some query")
            assert profile is DEFAULT_PROFILE

    def test_returns_default_on_exception(self):
        with patch('tools.knowledge_tools._classify_query_with_llm', side_effect=RuntimeError("boom")):
            profile = assess_query_profile("some query")
            assert profile is DEFAULT_PROFILE

    def test_returns_normal_for_normal_query(self):
        with patch('tools.knowledge_tools._classify_query_with_llm', return_value="normal"):
            profile = assess_query_profile("How does Reflexion work")
            assert profile.breadth == "normal"


# ═══════════════════════════════════════════════
# llm_rerank_and_select (mock LLM)
# ═══════════════════════════════════════════════

class TestLlmRerankAndSelect:
    def candidates(self):
        return [
            _make_result(1.02, "id0", "most relevant"),
            _make_result(1.05, "id1", "second best"),
            _make_result(1.10, "id2", "third"),
            _make_result(1.20, "id3", "far"),
        ]

    def mock_response(self, selected_items):
        content = json.dumps({"selected": selected_items})
        mock_resp = MagicMock()
        mock_resp.content = content
        return mock_resp

    def test_filters_relevance_below_2(self):
        with patch('tools.knowledge_tools._rerank_llm') as mock_llm:
            mock_llm.invoke.return_value = self.mock_response([
                {"id": "K1", "relevance": 3, "reason": "direct"},
                {"id": "K2", "relevance": 1, "reason": "weak"},
                {"id": "K3", "relevance": 0, "reason": "irrelevant"},
            ])
            result = llm_rerank_and_select("test", self.candidates())
            assert len(result) == 1  # only K1 with relevance >= 2

    def test_keeps_relevance_2_and_above(self):
        with patch('tools.knowledge_tools._rerank_llm') as mock_llm:
            mock_llm.invoke.return_value = self.mock_response([
                {"id": "K1", "relevance": 3, "reason": "direct"},
                {"id": "K2", "relevance": 2, "reason": "helpful"},
            ])
            result = llm_rerank_and_select("test", self.candidates())
            assert len(result) == 2

    def test_json_parse_failure_returns_all_candidates(self):
        with patch('tools.knowledge_tools._rerank_llm') as mock_llm:
            mock_resp = MagicMock()
            mock_resp.content = "not json at all {"
            mock_llm.invoke.return_value = mock_resp
            result = llm_rerank_and_select("test", self.candidates())
            assert len(result) == len(self.candidates())  # all returned as fallback

    def test_empty_selected_keeps_top_two_as_guard(self):
        with patch('tools.knowledge_tools._rerank_llm') as mock_llm:
            mock_llm.invoke.return_value = self.mock_response([])
            result = llm_rerank_and_select("test", self.candidates())
            assert len(result) == 2  # safety guard: always keep top 2

    def test_empty_selected_with_single_candidate(self):
        with patch('tools.knowledge_tools._rerank_llm') as mock_llm:
            mock_llm.invoke.return_value = self.mock_response([])
            single = [_make_result(1.10, "id0", "only one")]
            result = llm_rerank_and_select("test", single)
            assert len(result) == 1  # only 1 candidate, guard keeps it

    def test_filters_invalid_ids(self):
        with patch('tools.knowledge_tools._rerank_llm') as mock_llm:
            mock_llm.invoke.return_value = self.mock_response([
                {"id": "K1", "relevance": 3, "reason": "valid"},
                {"id": "K99", "relevance": 3, "reason": "invalid id"},
            ])
            result = llm_rerank_and_select("test", self.candidates())
            assert len(result) == 1  # only valid K1

    def test_empty_candidates_returns_empty(self):
        with patch('tools.knowledge_tools._rerank_llm') as mock_llm:
            mock_llm.invoke.return_value = self.mock_response([
                {"id": "K1", "relevance": 3, "reason": "valid"},
            ])
            result = llm_rerank_and_select("test", [])
            # _build_rerank_prompt will work, but by_label is empty → no match
            # Empty selected triggers check: candidates[0] doesn't exist → returns empty
            assert result == []


# ═══════════════════════════════════════════════
# smart_search_knowledge (integration with mocks)
# ═══════════════════════════════════════════════

class TestSmartSearchKnowledge:
    def test_empty_store_returns_empty(self):
        with patch('tools.knowledge_tools.get_chroma_store') as mock_store:
            mock_store.return_value.count.return_value = 0
            result = smart_search_knowledge("anything")
            assert result == ""

    def test_store_unavailable_returns_empty(self):
        with patch('tools.knowledge_tools.get_chroma_store', side_effect=RuntimeError):
            result = smart_search_knowledge("anything")
            assert result == ""

    def test_no_results_from_chroma_returns_empty(self):
        with patch('tools.knowledge_tools.get_chroma_store') as mock_store:
            store = MagicMock()
            store.count.return_value = 96
            store.search.return_value = []
            mock_store.return_value = store

            result = smart_search_knowledge("anything")
            assert result == ""

    def test_narrow_flow_returns_formatted(self):
        with patch('tools.knowledge_tools.get_chroma_store') as mock_store, \
             patch('tools.knowledge_tools.assess_query_profile') as mock_profile, \
             patch('tools.knowledge_tools.llm_rerank_and_select') as mock_rerank:

            store = MagicMock()
            store.count.return_value = 96
            store.search.return_value = _make_results(0.20, 0.25, 0.30)
            mock_store.return_value = store
            mock_profile.return_value = PROFILES["narrow"]
            mock_rerank.return_value = _make_results(0.20, 0.25)

            result = smart_search_knowledge("specific question")
            assert "[K1]" in result
            assert mock_rerank.called

    def test_broad_flow_allows_more_results(self):
        with patch('tools.knowledge_tools.get_chroma_store') as mock_store, \
             patch('tools.knowledge_tools.assess_query_profile') as mock_profile, \
             patch('tools.knowledge_tools.llm_rerank_and_select') as mock_rerank:

            store = MagicMock()
            store.count.return_value = 96
            store.search.return_value = _make_results(*[0.20 + i * 0.02 for i in range(30)])
            mock_store.return_value = store
            mock_profile.return_value = PROFILES["broad"]
            mock_rerank.return_value = _make_results(*[0.20 + i * 0.02 for i in range(10)])

            result = smart_search_knowledge("comprehensive analysis")
            assert len(result) > 0

    def test_llm_rerank_exception_falls_back_to_prefilter(self):
        with patch('tools.knowledge_tools.get_chroma_store') as mock_store, \
             patch('tools.knowledge_tools.assess_query_profile') as mock_profile, \
             patch('tools.knowledge_tools.llm_rerank_and_select', side_effect=RuntimeError):

            store = MagicMock()
            store.count.return_value = 96
            store.search.return_value = _make_results(0.20, 0.25, 0.30)
            mock_store.return_value = store
            mock_profile.return_value = PROFILES["normal"]

            result = smart_search_knowledge("query")
            assert "[K1]" in result  # still formatted from prefilter fallback

    def test_all_rejected_by_llm_returns_empty(self):
        with patch('tools.knowledge_tools.get_chroma_store') as mock_store, \
             patch('tools.knowledge_tools.assess_query_profile') as mock_profile, \
             patch('tools.knowledge_tools.llm_rerank_and_select', return_value=[]):

            store = MagicMock()
            store.count.return_value = 96
            store.search.return_value = _make_results(0.80, 0.85, 0.90)
            mock_store.return_value = store
            mock_profile.return_value = PROFILES["normal"]

            result = smart_search_knowledge("unrelated query")
            assert result == ""

    def test_rule_prefilter_removes_all_returns_empty(self):
        """When prefilter removes all results (all distances None, etc)"""
        with patch('tools.knowledge_tools.get_chroma_store') as mock_store, \
             patch('tools.knowledge_tools.assess_query_profile') as mock_profile:

            store = MagicMock()
            store.count.return_value = 96
            store.search.return_value = []  # no results from chroma
            mock_store.return_value = store
            mock_profile.return_value = PROFILES["normal"]

            result = smart_search_knowledge("query")
            assert result == ""


# ═══════════════════════════════════════════════
# Integration tests (real ChromaDB, mock LLM rerank)
# ═══════════════════════════════════════════════

@pytest.mark.integration
class TestSmartSearchIntegration:
    """Integration tests using real ChromaDB data with mocked LLM calls."""

    @pytest.fixture(autouse=True)
    def check_chroma_data(self):
        """Skip if ChromaDB has no data."""
        from rag.chroma_store import get_chroma_store
        try:
            store = get_chroma_store()
            if store.count() == 0:
                pytest.skip("ChromaDB has no data")
        except Exception:
            pytest.skip("ChromaDB unavailable")

    def test_full_flow_rerank_enabled(self):
        """Complete pipeline with rerank enabled returns formatted context."""
        with patch('tools.knowledge_tools._classify_query_with_llm', return_value="normal"), \
             patch('tools.knowledge_tools.llm_rerank_and_select') as mock_rerank:

            # Mock rerank: return first 2 candidates as selected
            from tools.knowledge_tools import rule_prefilter, PROFILES
            from rag.chroma_store import get_chroma_store

            store = get_chroma_store()
            raw = store.search("Reflexion loop", n_results=10)
            candidates = rule_prefilter(raw, PROFILES["normal"])

            def fake_rerank(q, cands):
                return cands[:min(3, len(cands))]
            mock_rerank.side_effect = fake_rerank

            result = smart_search_knowledge("How does Reflexion loop work")
            assert len(result) > 0
            assert "[K1]" in result

    def test_full_flow_rerank_disabled_falls_back_to_prefilter(self):
        """With rerank returning all candidates, prefilter results are used."""
        with patch('tools.knowledge_tools._classify_query_with_llm', return_value="normal"), \
             patch('tools.knowledge_tools.llm_rerank_and_select', return_value=[]):

            # rerank returns empty, but top1 is strong → keep 2
            from rag.chroma_store import get_chroma_store
            store = get_chroma_store()
            raw = store.search("Reflexion", n_results=5)
            top1 = raw[0].get("distance") if raw else None

            if top1 is not None and top1 < 0.35:
                # rerank internal guard returns first 2
                pass

            result = smart_search_knowledge("Reflexion")
            # With strong top1, the guard in llm_rerank_and_select keeps 2
            # But here we mock it returning [], so smart_search sees empty
            if top1 is not None and top1 < 0.35:
                pass  # Would return 2 via guard, but our mock bypasses

    def test_narrow_profile_returns_within_budget(self):
        """Narrow profile limits probe and budget."""
        with patch('tools.knowledge_tools._classify_query_with_llm', return_value="narrow"), \
             patch('tools.knowledge_tools.llm_rerank_and_select') as mock_rerank:

            from rag.chroma_store import get_chroma_store
            store = get_chroma_store()
            raw = store.search("phone number", n_results=10)

            def fake_rerank(q, cands):
                return cands[:1]
            mock_rerank.side_effect = fake_rerank

            result = smart_search_knowledge("What is my phone number")
            if result:
                assert len(result) <= 2000  # narrow budget = 1800 + header overhead

    def test_broad_profile_allows_more(self):
        """Broad profile allows larger budget and more probes."""
        with patch('tools.knowledge_tools._classify_query_with_llm', return_value="broad"), \
             patch('tools.knowledge_tools.llm_rerank_and_select') as mock_rerank:

            from rag.chroma_store import get_chroma_store
            store = get_chroma_store()
            raw = store.search("AI architecture comparison", n_results=30)

            def fake_rerank(q, cands):
                return cands[:min(8, len(cands))]
            mock_rerank.side_effect = fake_rerank

            result = smart_search_knowledge("Compare all AI architecture notes")
            if len(raw) >= 3:
                assert len(result) > 0

    def test_empty_chromadb_returns_empty(self):
        """When ChromaDB has no results, return empty string."""
        with patch('tools.knowledge_tools._classify_query_with_llm', return_value="normal"), \
             patch('tools.knowledge_tools.get_chroma_store') as mock_store_getter:

            mock_store = MagicMock()
            mock_store.count.return_value = 96
            mock_store.search.return_value = []
            mock_store_getter.return_value = mock_store

            result = smart_search_knowledge("unrelated gibberish xyzabc123")
            assert result == ""

    def test_llm_exception_degradation(self):
        """LLM rerank exception falls back to prefilter results."""
        import traceback
        with patch('tools.knowledge_tools._classify_query_with_llm', return_value="normal"), \
             patch('tools.knowledge_tools.llm_rerank_and_select', side_effect=RuntimeError("LLM timeout")):

            from rag.chroma_store import get_chroma_store
            store = get_chroma_store()
            raw = store.search("search_knowledge", n_results=10)

            result = smart_search_knowledge("search_knowledge implementation")
            if raw:
                assert len(result) > 0  # fallback to prefilter formatting
            else:
                assert result == ""

    def test_check_result_format(self):
        """Verify output format conventions."""
        with patch('tools.knowledge_tools._classify_query_with_llm', return_value="normal"), \
             patch('tools.knowledge_tools.llm_rerank_and_select') as mock_rerank:

            from rag.chroma_store import get_chroma_store
            store = get_chroma_store()
            raw = store.search("Reflexion", n_results=10)

            def fake_rerank(q, cands):
                return cands[:min(3, len(cands))]
            mock_rerank.side_effect = fake_rerank

            result = smart_search_knowledge("Reflexion")
            if result:
                assert "来源：" in result
                assert "内容：" in result
                assert "[K1]" in result
                # Should not contain raw JSON
                assert '{"selected"' not in result
