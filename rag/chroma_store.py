# rag/chroma_store.py
# Responsibility: Chroma vector database wrapper

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.errors import NotFoundError
from pathlib import Path


class ChromaStore:
    """Chroma vector store wrapper"""

    def __init__(self, persist_dir: str | Path, embedding_function=None):
        """
        persist_dir: Chroma data persistence directory (e.g. data/chroma/)
        embedding_function: Custom embedding function.
            If None, uses Chroma default ONNX model (downloads all-MiniLM-L6-v2).
            Recommended to pass OllamaEmbeddingFunction.
        """
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._embedding_function = embedding_function

    def get_collection(self, name: str = "personal_knowledge"):
        """Get or create collection (always use custom embedding function)"""
        try:
            col = self.client.get_collection(name)
            # Chroma doesn't preserve custom embedding function when getting existing collection
            # Replace with our own
            col._embedding_function = self._embedding_function
            return col
        except NotFoundError:
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
        """Write text chunks to Chroma"""
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
        """Search most relevant document chunks"""
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
        """Count documents in collection"""
        try:
            collection = self.get_collection(collection_name)
            return collection.count()
        except NotFoundError:
            return 0

    def delete_collection(self, collection_name: str = "personal_knowledge"):
        """Delete entire collection"""
        try:
            self.client.delete_collection(collection_name)
        except (ValueError, NotFoundError):
            pass


def get_chroma_store() -> ChromaStore:
    """Get production ChromaStore instance (using Ollama embedding)"""
    from config.settings import settings
    from llm.ollama_client import get_ollama_client

    client = get_ollama_client()
    embed_model = settings.ollama_embed_model

    class OllamaEmbed:
        """Use our own OllamaClient for embedding, compatible with Chroma interface"""
        def __call__(self, input: list[str]):
            return [client.embed(embed_model, text) for text in input]

    return ChromaStore(
        persist_dir=settings.chroma_path,
        embedding_function=OllamaEmbed(),
    )
