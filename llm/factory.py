# llm/factory.py
# v0.5: 统一 LLM 客户端工厂。所有 LLM 调用都走这里。

import httpx
from config.settings import settings


class UnifiedLLM:
    """统一的聊天客户端，封装 ollama / openai 兼容接口"""

    def __init__(self):
        self.provider = settings.llm_provider
        self.model = settings.llm_model
        self.base_url = settings.llm_base_url.rstrip("/")
        self.api_key = settings.llm_api_key

    def chat(self, messages: list[dict], system: str = None, temperature: float = 0.1,
             max_tokens: int = 2000) -> str:
        """统一 chat 接口，返回文本"""

        if self.provider == "ollama":
            return self._chat_ollama(messages, system, temperature)
        else:
            return self._chat_openai_compatible(messages, system, temperature, max_tokens)

    def _chat_ollama(self, messages, system, temperature):
        url = f"{self.base_url}/api/chat"
        payload = {"model": self.model, "messages": messages, "stream": False,
                   "options": {"temperature": temperature}}
        if system:
            payload["system"] = system
        resp = httpx.post(url, json=payload, timeout=300)
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def _chat_openai_compatible(self, messages, system, temperature, max_tokens):
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        payload = {"model": self.model, "messages": msgs, "temperature": temperature,
                   "max_tokens": max_tokens}
        resp = httpx.post(url, json=payload, headers=headers, timeout=300)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


# 单例 — 读取 settings 的值，修改 .env 后重建
_llm = None


def get_unified_llm() -> UnifiedLLM:
    global _llm
    _llm = UnifiedLLM()
    return _llm


def get_langchain_chat_model():
    """返回 LangChain 兼容的 ChatModel，用于 agent/graph.py"""
    provider = settings.llm_provider
    model = settings.llm_model
    base = settings.llm_base_url.rstrip("/")
    key = settings.llm_api_key

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=model, temperature=0, base_url=base)
    else:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, temperature=0, base_url=base, api_key=key)
