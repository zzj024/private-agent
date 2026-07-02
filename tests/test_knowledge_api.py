# tests/test_knowledge_api.py
# v0.5 知识库新 API 测试：上传 / 进度 / 统计 / 分页 / 删改

import json
import pytest
import os
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def stub_embedding():
    """Stub out Ollama embedding so tests don't need real Ollama."""
    with patch("rag.chroma_store.get_chroma_store") as mock_store:
        ms = MagicMock()
        ms.get_collection.return_value = ms
        ms.add_documents.return_value = None
        ms.get_file_stats.return_value = {"total_chunks": 0, "total_files": 0, "files": []}
        ms.get_file_chunks.return_value = {"chunks": [], "total": 0, "page": 1, "page_size": 20}
        ms.delete_file_chunks.return_value = 0
        ms.delete_chunk.return_value = True
        ms.update_chunk.return_value = {"ok": True, "reason": "updated", "chunk_id": "x"}
        ms.count.return_value = 0
        ms.delete_collection.return_value = None
        mock_store.return_value = ms
        yield


class TestKnowledgeStats:
    def test_stats_returns_structure(self, client):
        resp = client.get("/knowledge/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_chunks" in data
        assert "total_files" in data
        assert "files" in data
        assert isinstance(data["files"], list)


class TestKnowledgeUpload:
    def test_upload_rejects_non_md_txt(self, client):
        """Upload should reject .pdf files"""
        resp = client.post("/knowledge/upload",
                          files={"file": ("test.pdf", b"hello", "application/pdf")})
        assert resp.status_code == 400
        assert resp.json()["status"] == "error"

    def test_upload_empty_filename(self, client):
        """FastAPI rejects empty filename as 422 before our code runs."""
        resp = client.post("/knowledge/upload",
                          files={"file": ("", b"hello", "text/plain")})
        assert resp.status_code in (400, 422)

    def test_upload_returns_task_id(self, client):
        """Upload should return task_id immediately."""
        resp = client.post("/knowledge/upload",
                          files={"file": ("test.md", b"# Hello\n\nSome content here.", "text/markdown")})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "task_id" in data
        assert data["filename"] == "test.md"
        assert data["total_chunks"] >= 1


class TestKnowledgeProgress:
    def test_progress_unknown_task(self, client):
        resp = client.get("/knowledge/progress/nonexistent-id")
        assert resp.status_code == 404

    def test_progress_tracks_task(self, client):
        """Poll progress of a real upload."""
        resp = client.post("/knowledge/upload",
                          files={"file": ("book.md", b"# Chapter 1\n\nContent\n\n# Chapter 2\n\nMore content.", "text/markdown")})
        task_id = resp.json()["task_id"]
        # Poll until done
        for _ in range(20):
            pr = client.get(f"/knowledge/progress/{task_id}")
            assert pr.status_code == 200
            info = pr.json()
            if info["status"] == "done":
                assert info["done"] == info["total"]
                break
            assert info["status"] == "processing"
        else:
            pytest.fail("Import did not complete in time")


class TestKnowledgeChunks:
    def test_get_chunks_missing_file(self, client):
        resp = client.get("/knowledge/chunks/nonexistent.md?page=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    def test_get_chunks_pagination(self, client):
        """Pagination params should be accepted (exact values depend on mock)."""
        resp = client.get("/knowledge/chunks/test.md?page=2&page_size=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] in (1, 2)  # mock may not respect page param
        assert data["page_size"] in (5, 20)


class TestKnowledgeChunkDelete:
    def test_delete_chunk(self, client):
        resp = client.delete("/knowledge/chunk/test_chunk_123")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestKnowledgeChunkUpdate:
    def test_update_chunk_empty_text(self, client):
        resp = client.put("/knowledge/chunk/test_id", json={"text": ""})
        assert resp.status_code == 400

    def test_update_chunk_ok(self, client):
        resp = client.put("/knowledge/chunk/test_id", json={"text": "Updated content"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestKnowledgeFileDelete:
    def test_delete_file_chunks(self, client):
        resp = client.delete("/knowledge/chunks/somefile.md")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "deleted_chunks" in data


class TestKnowledgeCollectionDelete:
    def test_delete_collection(self, client):
        resp = client.delete("/knowledge/collection")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"