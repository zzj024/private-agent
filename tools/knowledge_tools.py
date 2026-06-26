# tools/knowledge_tools.py
# 职责：知识库检索工具——供 Agent 聊天时自动调用

from rag.chroma_store import get_chroma_store


N_RESULTS = 5
MAX_CONTEXT_CHARS = 3000


def search_knowledge(query: str) -> str:
    """
    搜索知识库，返回带编号的结构化上下文文本。
    如果知识库没有相关内容，返回空字符串。
    """
    try:
        store = get_chroma_store()
    except Exception:
        return ""

    if store.count() == 0:
        return ""

    try:
        results = store.search(query, n_results=N_RESULTS)
    except Exception:
        return ""

    if not results:
        return ""

    # 格式化成带编号的结构，方便 LLM 引用
    chunks = []
    total_chars = 0
    for i, r in enumerate(results, start=1):
        text = r["document"].strip()
        source = r["metadata"].get("source", "未知来源")
        header = r["metadata"].get("header", "")

        entry = f"[K{i}]"
        if header:
            entry += f"\n标题：{header}"
        entry += f"\n来源：{source}"
        entry += f"\n内容：\n{text}"

        if total_chars + len(entry) > MAX_CONTEXT_CHARS:
            break

        chunks.append(entry)
        total_chars += len(entry)

    if not chunks:
        return ""

    context = "以下是你的私有知识库检索结果：\n\n" + "\n\n".join(chunks)
    return context
