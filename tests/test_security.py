# tests/test_security.py
# Responsibility: Security tests for input validation and error handling

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestInputValidation:
    """Test input validation"""

    def test_empty_message(self, client):
        """Security: Empty message handled gracefully"""
        resp = client.post("/chat", json={"message": ""})
        assert resp.status_code == 200

    def test_long_message(self, client):
        """Security: Long message handled gracefully"""
        long_message = "A" * 10000
        resp = client.post("/chat", json={"message": long_message})
        assert resp.status_code == 200

    def test_special_characters(self, client):
        """Security: Special characters handled gracefully"""
        resp = client.post("/chat", json={"message": "<script>alert('xss')</script>"})
        assert resp.status_code == 200


class TestErrorHandling:
    """Test error handling"""

    def test_invalid_conversation_id(self, client):
        """Security: Invalid conversation ID handled gracefully"""
        resp = client.post("/chat", json={
            "message": "Hello",
            "conversation_id": "invalid-id-12345"
        })
        assert resp.status_code == 200

    def test_missing_fields(self, client):
        """Security: Missing fields handled gracefully"""
        resp = client.post("/chat", json={})
        assert resp.status_code == 422  # Validation error
