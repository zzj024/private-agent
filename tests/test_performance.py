# tests/test_performance.py
# Responsibility: Performance tests for response time and concurrency

import pytest
import time
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestResponseTime:
    """Test response time"""

    def test_chat_response_time(self, client):
        """Performance: Chat response time < 30 seconds"""
        start = time.time()
        resp = client.post("/chat", json={"message": "Hello"})
        end = time.time()
        
        assert resp.status_code == 200
        assert end - start < 30  # 30 seconds max

    def test_memory_list_response_time(self, client):
        """Performance: Memory list response time < 1 second"""
        start = time.time()
        resp = client.get("/memory/list")
        end = time.time()
        
        assert resp.status_code == 200
        assert end - start < 1  # 1 second max


class TestConcurrency:
    """Test concurrent requests"""

    def test_concurrent_chat_requests(self, client):
        """Performance: Handle 3 concurrent chat requests"""
        def send_chat():
            return client.post("/chat", json={"message": "Hello"})
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(send_chat) for _ in range(3)]
            results = [f.result() for f in futures]
        
        # All should succeed
        for resp in results:
            assert resp.status_code == 200
