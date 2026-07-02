# 职责：封装 Ollama HTTP API 调用

import json
import httpx
from typing import Optional

class OllamaClient:
    """Ollama 本地模型的 HTTP 客户端"""
    def __init__(self, base_url: str = "http://127.0.0.1:11434"):
        self.base_url = base_url.rstrip("/")

    def chat(self, model: str, messages: list[dict],
            system: Optional[str] = None ,stream: bool = False) -> str:
        """发送聊天请求，返回模型回答文本"""

        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }

        if system: 
            payload["system"] = system

        response = httpx.post(url, json=payload, timeout=120)
        response.raise_for_status()

        data = response.json()
        return data["message"]["content"]

    def chat_stream(self,model: str,
        messages: list[dict], system: Optional[str] = None):
        """流式聊天，逐块yield回答文本"""
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if system: 
            payload["system"] = system

        with httpx.stream("POST", url, json=payload, timeout=120) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line: 
                    continue
                data = json.loads(line)
                if not data.get("done", False):
                    yield data["message"]["content"]

    def embed(self, model: str, text: str) -> list[float]:
        """单条文本 → 向量（慢，保留兼容）"""
        return self.embed_batch(model, [text])[0]

    def embed_batch(self, model: str, texts: list[str]) -> list[list[float]]:
        """批量文本 → 向量。Ollama /api/embed 原生支持数组 input，一次请求处理全部。"""
        url = f"{self.base_url}/api/embed"
        payload = {"model": model, "input": texts}
        response = httpx.post(url, json=payload, timeout=300)
        response.raise_for_status()
        return response.json()["embeddings"]

def get_ollama_client() -> OllamaClient:
    """获取 OllamaClient 实例"""
    from config.settings import settings
    return OllamaClient(base_url=settings.ollama_base_url)
