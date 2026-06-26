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
        """将文本转化为向量embedding，用于chroma检索"""
        url = f"{self.base_url}/api/embed"
        payload = {
            "model": model,
            "input": text,
        }
        response = httpx.post(url, json=payload, timeout=30)
        response.raise_for_status()

        data = response.json()
        return data["embeddings"][0]

def get_ollama_client() -> OllamaClient:
    """获取 OllamaClient 实例"""
    from config.settings import settings
    return OllamaClient(base_url=settings.ollama_base_url)
