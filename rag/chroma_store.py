# rag/chroma_store.py
# 职责：封装 Chroma 向量数据库的增删改查

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.errors import InvalidCollectionException
from pathlib import Path


class ChromaStore:
    """Chroma 向量库封装"""

    def __init__(self, persist_dir: str | Path, embedding_function=None):
        """
        persist_dir: Chroma 数据持久化目录（如 data/chroma/）
        embedding_function: 自定义 embedding 函数。
            传 None 则使用 Chroma 默认的 ONNX 模型（会下载 all-MiniLM-L6-v2）。
            推荐传入 OllamaEmbeddingFunction。
        """
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._embedding_function = embedding_function

    def get_collection(self, name: str = "personal_knowledge"):
        """获取或创建集合（始终使用自定义 embedding 函数）"""
        try:
            col = self.client.get_collection(name)
            # Chroma 获取已有集合时不会保留自定义 embedding 函数
            # 替换成我们自己的
            col._embedding_function = self._embedding_function
            return col
        except InvalidCollectionException:
            return self.client.create_collection(
                name=name,
                embedding_function=self._embedding_function,
            )

    def add_documents(
        self,
        texts: list[str],
        metadatas: list[dict],
        ids: list[str],
        collection_name: str = "personal_knowledge",
    ):
        """将文本块写入 Chroma"""
        if not texts:
            return
        collection = self.get_collection(collection_name)
        collection.add(
            documents=texts,
            metadatas=metadatas,
            ids=ids,
        )

    def search(
        self,
        query: str,
        n_results: int = 5,
        collection_name: str = "personal_knowledge",
    ) -> list[dict]:
        """搜索最相关的文档块"""
        collection = self.get_collection(collection_name)

        if collection.count() == 0:
            return []

        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, collection.count()),
        )

        output = []
        for i in range(len(results["ids"][0])):
            output.append({
                "id": results["ids"][0][i],
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })
        return output

    def count(self, collection_name: str = "personal_knowledge") -> int:
        """统计集合中的文档数量"""
        try:
            collection = self.get_collection(collection_name)
            return collection.count()
        except InvalidCollectionException:
            return 0

    def delete_collection(self, collection_name: str = "personal_knowledge"):
        """删除整个集合"""
        try:
            self.client.delete_collection(collection_name)
        except ValueError:
            pass


def get_chroma_store() -> ChromaStore:
    """获取生产环境 ChromaStore 实例（使用 Ollama embedding）"""
    from config.settings import settings
    from llm.ollama_client import get_ollama_client

    client = get_ollama_client()
    embed_model = settings.ollama_embed_model

    class OllamaEmbed:
        """用我们自己的 OllamaClient 做 embedding，兼容 Chroma 接口"""
        def __call__(self, input: list[str]):
            return [client.embed(embed_model, text) for text in input]

    return ChromaStore(
        persist_dir=settings.chroma_path,
        embedding_function=OllamaEmbed(),
    )
