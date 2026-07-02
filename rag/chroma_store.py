# rag/chroma_store.py
# Responsibility: Chroma vector database wrapper (v0.5 — singleton + thread-safe)

import logging
import threading
from pathlib import Path
from functools import lru_cache

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.errors import NotFoundError, InvalidCollectionException

logger = logging.getLogger(__name__)


class ChromaStore:
    """Chroma vector store wrapper — v0.5: single-instance + write-locked."""

    _write_lock = threading.RLock()

    def __init__(self, persist_dir: str | Path, embedding_function=None):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._embedding_function = embedding_function

    def get_or_create_collection(self, name: str = "personal_knowledge"):
        """Use ONLY for import/ingest. Creates collection if missing."""
        try:
            col = self.client.get_collection(name)
            col._embedding_function = self._embedding_function
            return col
        except (NotFoundError, InvalidCollectionException):
            return self.client.create_collection(
                name=name,
                embedding_function=self._embedding_function,
            )

    def require_collection(self, name: str = "personal_knowledge"):
        """Use for read/update/delete. Never auto-creates."""
        col = self.client.get_collection(name)
        col._embedding_function = self._embedding_function
        return col

    # ── write helpers ────────────────────────────────────────────

    def add_documents(self, texts, metadatas, ids, collection_name="personal_knowledge"):
        if not texts:
            return
        with self._write_lock:
            col = self.get_or_create_collection(collection_name)
            col.add(documents=texts, metadatas=metadatas, ids=ids)

    # ── read helpers ─────────────────────────────────────────────

    def search(self, query, n_results=5, collection_name="personal_knowledge") -> list[dict]:
        try:
            col = self.require_collection(collection_name)
        except (NotFoundError, InvalidCollectionException):
            return []

        if col.count() == 0:
            return []

        results = col.query(query_texts=[query], n_results=min(n_results, col.count()))
        output = []
        for i in range(len(results["ids"][0])):
            output.append({
                "id": results["ids"][0][i],
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })
        return output

    def count(self, collection_name="personal_knowledge") -> int:
        try:
            return self.require_collection(collection_name).count()
        except (NotFoundError, InvalidCollectionException):
            return 0

    # ── stats / browse ───────────────────────────────────────────

    def get_file_stats(self, collection_name="personal_knowledge") -> dict:
        from collections import Counter
        try:
            col = self.require_collection(collection_name)
        except (NotFoundError, InvalidCollectionException):
            return {"total_chunks": 0, "total_files": 0, "files": []}

        data = col.get(include=["metadatas"])
        ids_list = data.get("ids") or []
        metas = data.get("metadatas") or []
        counter = Counter()
        for m in metas:
            m = m or {}
            fname = Path(str(m.get("source", "unknown"))).name
            counter[fname] += 1
        files = [{"name": n, "chunks": c} for n, c in sorted(counter.items(), key=lambda x: x[0].lower())]
        return {"total_chunks": len(ids_list), "total_files": len(files), "files": files}

    def get_file_chunks(self, filename, page=1, page_size=20, collection_name="personal_knowledge") -> dict:
        safe_name = Path(str(filename)).name
        try:
            col = self.require_collection(collection_name)
        except (NotFoundError, InvalidCollectionException):
            return {"chunks": [], "total": 0, "page": page, "page_size": page_size}

        data = col.get(include=["metadatas", "documents"])
        ids_list = data.get("ids") or []
        docs = data.get("documents") or []
        metas = data.get("metadatas") or []
        matched = []
        for cid, doc, m in zip(ids_list, docs, metas):
            m = m or {}
            if Path(str(m.get("source", ""))).name == safe_name:
                matched.append({"id": cid, "text": doc, "header": m.get("header", ""), "source": m.get("source", "")})
        total = len(matched)
        start = (page - 1) * page_size
        return {"chunks": matched[start:start + page_size], "total": total, "page": page, "page_size": page_size}

    # ── delete ───────────────────────────────────────────────────

    def delete_file_chunks(self, filename, collection_name="personal_knowledge") -> int:
        safe_name = Path(str(filename)).name
        try:
            col = self.require_collection(collection_name)
        except (NotFoundError, InvalidCollectionException):
            return 0
        data = col.get(include=["metadatas"])
        to_delete = []
        for cid, m in zip(data.get("ids") or [], data.get("metadatas") or []):
            if Path(str((m or {}).get("source", ""))).name == safe_name:
                to_delete.append(cid)
        if to_delete:
            with self._write_lock:
                col.delete(ids=to_delete)
        return len(to_delete)

    def delete_chunk(self, chunk_id, collection_name="personal_knowledge") -> bool:
        try:
            col = self.require_collection(collection_name)
        except (NotFoundError, InvalidCollectionException):
            return False
        with self._write_lock:
            col.delete(ids=[chunk_id])
        return True

    def delete_collection(self, collection_name="personal_knowledge"):
        try:
            self.client.delete_collection(collection_name)
        except (ValueError, NotFoundError, InvalidCollectionException):
            pass

    # ── update (v0.5 fix: use col.update, not delete+add) ────────

    def update_chunk(self, chunk_id, new_text, collection_name="personal_knowledge") -> dict:
        """Update a single chunk. Returns {ok, reason, chunk_id}."""
        if not new_text or not new_text.strip():
            return {"ok": False, "reason": "empty_text", "chunk_id": chunk_id}

        try:
            col = self.require_collection(collection_name)
        except (NotFoundError, InvalidCollectionException) as e:
            logger.error("update_chunk: collection not found name=%r err=%s", collection_name, e)
            return {"ok": False, "reason": "collection_not_found", "chunk_id": chunk_id, "collection": collection_name}

        with self._write_lock:
            existing = col.get(ids=[chunk_id], include=["metadatas"])
            if not existing.get("ids"):
                return {"ok": False, "reason": "not_found", "chunk_id": chunk_id, "collection": collection_name}

            old_meta = (existing.get("metadatas") or [{}])[0] or {}

            try:
                col.update(ids=[chunk_id], documents=[new_text], metadatas=[old_meta])
                return {"ok": True, "reason": "updated", "chunk_id": chunk_id, "collection": collection_name}
            except Exception as e:
                logger.exception("update_chunk failed: chunk_id=%r collection=%r", chunk_id, collection_name)
                return {"ok": False, "reason": "exception", "error": repr(e), "chunk_id": chunk_id, "collection": collection_name}


# ── singleton factory ──────────────────────────────────────────

@lru_cache(maxsize=1)
def get_chroma_store() -> ChromaStore:
    """Get singleton ChromaStore instance (cached)."""
    from config.settings import settings
    from llm.ollama_client import get_ollama_client

    client = get_ollama_client()
    embed_model = settings.ollama_embed_model

    class OllamaEmbed:
        def __call__(self, input: list[str]):
            return client.embed_batch(embed_model, input)

    return ChromaStore(persist_dir=settings.chroma_path, embedding_function=OllamaEmbed())
