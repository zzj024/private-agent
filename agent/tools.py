# agent/tools.py
# Responsibility: @tool decorated tool functions for LangGraph bind_tools()

from langchain_core.tools import tool


@tool
def search_knowledge(query: str) -> str:
    """搜索私有知识库（带缓存）"""
    # 1. 获取当前 state
    from agent.reflexion import get_current_state
    state = get_current_state()
    
    if state:
        # 2. 检查缓存
        cached = state.get_cached_tool_result("kb_v2", query)
        if cached:
            return cached  # 缓存命中
    
    # 3. 缓存没有，查数据库
    from tools.knowledge_tools import search_knowledge as kb_search
    result = kb_search(query)
    
    # 4. 存入缓存
    if state:
        state.cache_tool_result("kb_v2", query, result)
    
    return result


@tool
def save_memory(key: str, value: str, category: str = "preference") -> str:
    """保存一条长期记忆"""
    from memory.sqlite_store import get_store
    store = get_store()
    store.save_memory(key, value, category)
    
    # 清除相关缓存
    from agent.reflexion import get_current_state
    state = get_current_state()
    if state:
        state.clear_cache("memory:")
    
    return f"Saved: {key} = {value}"


@tool
def list_memories(category: str = "") -> str:
    """列出用户的长期记忆（带缓存）"""
    # 1. 获取当前 state
    from agent.reflexion import get_current_state
    state = get_current_state()
    
    cache_key = f"memory:list:{category}"
    if state:
        # 2. 检查缓存
        cached = state.get_cached_tool_result("memory", cache_key)
        if cached:
            return cached  # 缓存命中
    
    # 3. 缓存没有，查数据库
    from memory.sqlite_store import get_store
    store = get_store()
    cat = category or None
    memories = store.list_memories(cat)
    if not memories:
        return "No memories"
    parts = []
    for m in memories:
        k = m["key"]
        v = m["value"]
        c = m["category"]
        parts.append(f"- {k}: {v} ({c})")
    result = "\n".join(parts)
    
    # 4. 存入缓存
    if state:
        state.cache_tool_result("memory", cache_key, result)
    
    return result


@tool
def delete_memory(key: str) -> str:
    """删除指定 key 的长期记忆"""
    from memory.sqlite_store import get_store
    store = get_store()
    success = store.delete_memory(key)
    
    # 清除相关缓存
    from agent.reflexion import get_current_state
    state = get_current_state()
    if state:
        state.clear_cache("memory:")
    
    if success:
        return f"Deleted memory: {key}"
    return f"Memory not found: {key}"


@tool
def delete_all_memories() -> str:
    """删除全部长期记忆"""
    from memory.sqlite_store import get_store
    store = get_store()
    memories = store.list_memories()
    if not memories:
        return "No memories to delete"
    for m in memories:
        store.delete_memory(m["key"])
    
    # 清除相关缓存
    from agent.reflexion import get_current_state
    state = get_current_state()
    if state:
        state.clear_cache("memory:")
    
    return f"Deleted all {len(memories)} memories"


# 工具注册列表
TOOLS = [search_knowledge, save_memory, list_memories, delete_memory, delete_all_memories]