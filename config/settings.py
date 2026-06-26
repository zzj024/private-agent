# 职责： 全局配置管理，所有模块从这里读取配置

from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    # 项目路径
    project_root: Path = Path(__file__).parent.parent

    # llm配置
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "qwen2.5:7b"
    ollama_embed_model: str = "nomic-embed-text"

    # 存储配置
    sqlite_path: Path = project_root / "data" / "agent.db"
    chroma_path: Path = project_root / "data" / "chroma"
    raw_docs_path: Path = project_root / "data" / "raw_docs"

    # api密钥
    deepseek_api_key: str = ""

    # 服务配置
    host: str= "127.0.0.1"
    port: int = 8000

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8"
    }


# 全局单例，其他模块 from config.settings import settings 使用
settings = Settings()