# tests/test_e2e.py
# Responsibility: End-to-end tests for complete user flows

import pytest
import json
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestChatE2E:
    """Test complete chat flow"""

    def test_chat_simple_question(self, client):
        """E2E: Simple chat question"""
        resp = client.post("/chat", json={"message": "Hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert data["response"] is not None

    def test_chat_with_conversation_id(self, client):
        """E2E: Chat with conversation ID"""
        resp = client.post("/chat", json={
            "message": "Hello",
            "conversation_id": "test-conv-1"
        })
        assert resp.status_code == 200

    def test_chat_stream(self, client):
        """E2E: Stream chat"""
        resp = client.post("/chat/stream", json={"message": "Hello"})
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]


class TestMemoryE2E:
    """Test complete memory flow"""

    def test_save_and_query_memory(self, client):
        """E2E: Save memory and query it"""
        # Save memory
        resp = client.post("/memory/remember", json={
            "key": "test_key",
            "value": "test_value",
            "category": "preference"
        })
        assert resp.status_code == 200
        
        # Query memory
        resp = client.get("/memory/list")
        assert resp.status_code == 200
        data = resp.json()
        assert "memories" in data
        
        # Cleanup
        client.delete("/memory/delete/test_key")

    def test_delete_memory(self, client):
        """E2E: Delete memory"""
        # Save first
        client.post("/memory/remember", json={
            "key": "to_delete",
            "value": "value",
            "category": "preference"
        })
        
        # Delete
        resp = client.delete("/memory/delete/to_delete")
        assert resp.status_code == 200


class TestKnowledgeE2E:
    """Test complete knowledge base flow"""

    def test_search_knowledge(self, client):
        """E2E: Search knowledge base"""
        resp = client.post("/knowledge/search", json={
            "query": "Python",
            "top_k": 5
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "context" in data


class TestHealthE2E:
    """Test health check"""

    def test_health_check(self, client):
        """E2E: Health check endpoint"""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
