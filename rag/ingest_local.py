# rag/ingest_local.py
# 职责：扫描 knowledge/ 目录，导入本地笔记到 Chroma

from pathlib import Path
from rag.chunker import Chunker
from rag.chroma_store import ChromaStore


def ingest_local_directory(
    directory: str | Path,
    chroma_store: ChromaStore,
    collection_name: str = "personal_knowledge",
) -> dict:
    """
    导入本地目录下的所有 .md / .txt 文件到 Chroma。

    参数：
        directory:      要扫描的目录路径（如 "knowledge/"）
        chroma_store:   ChromaStore 实例
        collection_name: 目标集合名称

    返回：
        {"files": 文件数, "chunks": 总块数, "imported": 成功导入块数}
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        return {"error": f"目录不存在: {directory}"}

    chunker = Chunker(chunk_size=300, overlap=50)
    all_chunks = []

    # 扫描所有 .md 和 .txt 文件
    files = list(dir_path.rglob("*.md")) + list(dir_path.rglob("*.txt"))
    if not files:
        return {"files": 0, "chunks": 0, "imported": 0, "message": "未找到 .md 或 .txt 文件"}

    # 遍历每个文件，切块
    for file_path in files:
        chunks = chunker.chunk_file(file_path)
        all_chunks.extend(chunks)

    if not all_chunks:
        return {"files": len(files), "chunks": 0, "imported": 0}

    # 准备 Chroma 数据
    texts = [c.text for c in all_chunks]
    metadatas = [c.metadata for c in all_chunks]
    ids = [f"{c.metadata['source']}_{i}" for i, c in enumerate(all_chunks)]

    chroma_store.add_documents(
        texts=texts,
        metadatas=metadatas,
        ids=ids,
        collection_name=collection_name,
    )

    return {
        "files": len(files),
        "chunks": len(all_chunks),
        "imported": len(all_chunks),
        "message": f"成功导入 {len(files)} 个文件，共 {len(all_chunks)} 个文本块",
    }


def ingest_local_file(
    file_path: str | Path,
    chroma_store: ChromaStore,
    collection_name: str = "personal_knowledge",
) -> dict:
    """导入单个 .md / .txt 文件到 Chroma"""
    path = Path(file_path)
    if not path.exists():
        return {"error": f"文件不存在: {file_path}"}

    chunker = Chunker(chunk_size=300, overlap=50)
    chunks = chunker.chunk_file(path)

    if not chunks:
        return {"files": 0, "chunks": 0, "imported": 0}

    texts = [c.text for c in chunks]
    metadatas = [c.metadata for c in chunks]
    ids = [f"{path.name}_{i}" for i in range(len(chunks))]

    chroma_store.add_documents(
        texts=texts,
        metadatas=metadatas,
        ids=ids,
        collection_name=collection_name,
    )

    return {
        "files": 1,
        "chunks": len(chunks),
        "imported": len(chunks),
        "message": f"成功导入 {path.name}，共 {len(chunks)} 个文本块",
    }
