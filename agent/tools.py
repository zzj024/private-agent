# agent/tools.py
# 职责：@tool 装饰器定义的工具函数，供 LangGraph bind_tools() 使用

from langchain_core.tools import tool


@tool
def search_knowledge(query: str) -> str:
    """搜索私有知识库。当需要查询用户的笔记、文档或项目信息时使用。"""
    from tools.knowledge_tools import search_knowledge as kb_search
    return kb_search(query)


@tool
def save_memory(key: str, value: str, category: str = "preference") -> str:
    """保存一条长期记忆。key 是类别（姓名/技术栈/薄弱点/目标/偏好），value 是具体内容。"""
    from memory.sqlite_store import get_store
    store = get_store()
    store.save_memory(key, value, category)
    return f"已记住：{key} = {value}"


@tool
def list_memories(category: str = "") -> str:
    """列出用户的长期记忆。可指定分类筛选。"""
    from memory.sqlite_store import get_store
    store = get_store()
    cat = category or None
    memories = store.list_memories(cat)
    if not memories:
        return "暂无记忆"
    parts = []
    for m in memories:
        k = m["key"]
        v = m["value"]
        c = m["category"]
        parts.append(f"- {k}: {v} ({c})")
    return "\n".join(parts)


@tool
def delete_memory(key: str) -> str:
    """删除指定 key 的长期记忆。"""
    from memory.sqlite_store import get_store
    store = get_store()
    success = store.delete_memory(key)
    if success:
        return f"已删除记忆：{key}"
    return f"未找到记忆：{key}"


@tool
def delete_all_memories() -> str:
    """删除全部长期记忆。此操作不可撤销，需要用户确认。"""
    from memory.sqlite_store import get_store
    store = get_store()
    memories = store.list_memories()
    if not memories:
        return "暂无记忆可删除"
    for m in memories:
        store.delete_memory(m["key"])
    return f"已删除全部 {len(memories)} 条记忆"



# 工具注册列表
TOOLS = [search_knowledge, save_memory, list_memories, delete_memory, delete_all_memories]
