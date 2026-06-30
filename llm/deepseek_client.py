import httpx
from config.settings import settings


class DeepSeekClient:
    """DeepSeek API 客户端"""

    def __init__(self):
        self.base_url = settings.deepseek_base_url.rstrip("/")
        self.api_key = settings.deepseek_api_key
        self.model = settings.deepseek_model

    def chat(self, prompt: str, system: str = None) -> str:
        """调用 DeepSeek API"""
        if not self.api_key:
            raise RuntimeError("DeepSeek API key 未配置，请在 .env 中设置 DEEPSEEK_API_KEY")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        data = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 2000
        }

        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=data
                )
                response.raise_for_status()
                result = response.json()
                return result["choices"][0]["message"]["content"]

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 401:
                raise RuntimeError("DeepSeek API key 无效，请检查 .env 中的 DEEPSEEK_API_KEY")
            elif status == 429:
                raise RuntimeError("DeepSeek API 调用频率超限，请稍后重试")
            elif status >= 500:
                raise RuntimeError(f"DeepSeek 服务异常 (HTTP {status})，请稍后重试")
            else:
                raise RuntimeError(f"DeepSeek API 请求失败 (HTTP {status}): {e.response.text[:200]}")

        except httpx.TimeoutException:
            raise RuntimeError("DeepSeek API 请求超时，请检查网络或稍后重试")

        except httpx.RequestError as e:
            raise RuntimeError(f"网络连接失败: {str(e)[:200]}")


# 单例
_client = None


def get_deepseek_client() -> DeepSeekClient:
    """获取 DeepSeek 客户端单例"""
    global _client
    if _client is None:
        _client = DeepSeekClient()
    return _client
