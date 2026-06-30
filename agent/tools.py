# agent/tools.py
# Responsibility: @tool decorated tool functions for LangGraph bind_tools()

from langchain_core.tools import tool


@tool
def search_knowledge(query: str) -> str:
    """Search private knowledge base. Use when you need to query user notes, documents, or project information."""
    from tools.knowledge_tools import search_knowledge as kb_search
    return kb_search(query)


@tool
def save_memory(key: str, value: str, category: str = "preference") -> str:
    """Save a long-term memory. key is category (name/tech_stack/weak_point/goal/preference), value is specific content."""
    from memory.sqlite_store import get_store
    store = get_store()
    store.save_memory(key, value, category)
    return f"Saved: {key} = {value}"


@tool
def list_memories(category: str = "") -> str:
    """List user long-term memories. Can specify category to filter."""
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
    return "\n".join(parts)


@tool
def delete_memory(key: str) -> str:
    """Delete a long-term memory by key."""
    from memory.sqlite_store import get_store
    store = get_store()
    success = store.delete_memory(key)
    if success:
        return f"Deleted memory: {key}"
    return f"Memory not found: {key}"


@tool
def delete_all_memories() -> str:
    """Delete all long-term memories. This operation is irreversible, requires user confirmation."""
    from memory.sqlite_store import get_store
    store = get_store()
    memories = store.list_memories()
    if not memories:
        return "No memories to delete"
    for m in memories:
        store.delete_memory(m["key"])
    return f"Deleted all {len(memories)} memories"


# Tool registration list
TOOLS = [search_knowledge, save_memory, list_memories, delete_memory, delete_all_memories]
