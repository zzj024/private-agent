# 职责：全局配置管理，所有模块从这里读取配置

from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    # 项目路径
    project_root: Path = Path(__file__).parent.parent

    # ═══════════════════════════════════════════════
    # 统一 LLM 配置（v0.5 — 全局共用）
    # ═══════════════════════════════════════════════
    llm_provider: str = "ollama"          # ollama | deepseek | moonshot
    llm_model: str = "qwen2.5:7b"        # 模型名
    llm_base_url: str = "http://127.0.0.1:11434"  # API 地址
    llm_api_key: str = ""                 # 远端 API 需要

    # Ollama（兼容旧配置）
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "qwen2.5:7b"
    ollama_embed_model: str = "nomic-embed-text"

    # DeepSeek（兼容旧配置）
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"

    # Reflexion 循环参数
    reflexion_max_retries: int = 3
    reflexion_min_score: int = 4
    reflexion_pass_score: int = 7

    # 存储路径
    sqlite_path: Path = project_root / "data" / "agent.db"
    chroma_path: Path = project_root / "data" / "chroma"

    # 被动记忆提取
    passive_memory_enabled: bool = True
    # 自动分级阈值：LLM 自评 confidence ≥ 此值 → 直接写入正式记忆
    passive_memory_auto_accept_threshold: float = 0.85
    # 自动分级阈值：LLM 自评 confidence < 此值 → 直接丢弃（不产生噪音）
    passive_memory_auto_reject_threshold: float = 0.60

    # 服务
    host: str = "127.0.0.1"
    port: int = 8000

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8"
    }


# 全局单例，其他模块 from config.settings import settings 使用
settings = Settings()
