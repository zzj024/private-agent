"""Test passive memory API endpoints."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestListCandidates:
    def test_list_pending(self, client):
        mock = MagicMock()
        mock.list_memory_candidates.return_value = [
            {"id": 1, "key": "k1", "value": "v1", "status": "pending"},
        ]
        with patch("app.main.get_store", return_value=mock):
            resp = client.get("/memory/candidates?status=pending")
            assert resp.status_code == 200
            assert len(resp.json()["candidates"]) == 1

    def test_list_empty(self, client):
        mock = MagicMock()
        mock.list_memory_candidates.return_value = []
        with patch("app.main.get_store", return_value=mock):
            resp = client.get("/memory/candidates")
            assert resp.status_code == 200
            assert resp.json()["candidates"] == []


class TestAcceptCandidate:
    def test_accept_success(self, client):
        mock = MagicMock()
        mock.get_memory_candidate.return_value = {
            "id": 1, "key": "k1", "value": "v1", "category": "pref",
            "confidence": 0.9, "evidence": "ev", "status": "pending",
            "source_conversation_id": 1, "source_message_ids": "[1]",
        }
        with patch("app.main.get_store", return_value=mock):
            resp = client.post("/memory/candidates/1/accept")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
            mock.save_memory.assert_called_once()
            mock.update_memory_candidate_status.assert_called_once_with(
                1, "accepted")

    def test_accept_not_found(self, client):
        mock = MagicMock()
        mock.get_memory_candidate.return_value = None
        with patch("app.main.get_store", return_value=mock):
            resp = client.post("/memory/candidates/999/accept")
            assert resp.status_code == 404

    def test_accept_already_processed(self, client):
        mock = MagicMock()
        mock.get_memory_candidate.return_value = {
            "id": 1, "key": "k1", "value": "v1", "status": "accepted",
        }
        with patch("app.main.get_store", return_value=mock):
            resp = client.post("/memory/candidates/1/accept")
            assert resp.status_code == 400


class TestRejectCandidate:
    def test_reject_success(self, client):
        mock = MagicMock()
        mock.get_memory_candidate.return_value = {
            "id": 1, "key": "k1", "value": "v1", "status": "pending",
        }
        with patch("app.main.get_store", return_value=mock):
            resp = client.post("/memory/candidates/1/reject")
            assert resp.status_code == 200
            mock.update_memory_candidate_status.assert_called_once_with(
                1, "rejected")

    def test_reject_not_found(self, client):
        mock = MagicMock()
        mock.get_memory_candidate.return_value = None
        with patch("app.main.get_store", return_value=mock):
            resp = client.post("/memory/candidates/999/reject")
            assert resp.status_code == 404
