# agent/graph.py
# Responsibility: LangGraph workflow - ReAct loop (Reasoning-Action-Observation)

import uuid
import re
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from agent.tools import TOOLS
from config.settings import settings


# ═══════════════════════════════════════════════
# Utility functions
# ═══════════════════════════════════════════════

def normalize_answer(text: str) -> str:
    """Normalize LLM answer Markdown format"""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").strip()
    # Add blank line after colon (e.g., "Answer:" -> "Answer:\n")
    text = re.sub(r":\n(?!\n)", r":\n\n", text)
    # Remove multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ═══════════════════════════════════════════════
# Build ReAct Agent
# ═══════════════════════════════════════════════

def build_agent():
    """Build ReAct Agent — v0.5: use unified LLM config"""
    from llm.factory import get_langchain_chat_model
    llm = get_langchain_chat_model()

    agent = create_react_agent(
        model=llm,
        tools=TOOLS,
    )

    return agent


# Build at module load time
agent = build_agent()


# ═══════════════════════════════════════════════
# Run entry points
# ═══════════════════════════════════════════════

def _load_conversation_messages(conversation_id: int | None) -> list:
    """Load conversation history from DB, return as LangChain message list."""
    if not conversation_id:
        return []
    try:
        from memory.sqlite_store import get_store
        store = get_store()
        raw = store.get_conversation_messages(conversation_id)
        messages = []
        for m in raw:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                from langchain_core.messages import AIMessage
                messages.append(AIMessage(content=content))
        return messages
    except Exception:
        return []


def _load_user_memories() -> str:
    """Load all confirmed memories and format as context text."""
    try:
        from memory.sqlite_store import get_store
        store = get_store()
        memories = store.list_memories()
        if not memories:
            return ""
        lines = ["[关于用户的已知信息]"]
        for m in memories:
            cat = m.get("category", "")
            key = m.get("key", "")
            value = m.get("value", "")
            lines.append(f"- [{cat}] {key}: {value}")
        return "\n".join(lines)
    except Exception:
        return ""


def run_agent(message: str, conversation_id: int | None = None,
              history: list = None, memory_context: str = "") -> str:
    """Run Agent (v0.2 ReAct)

    Args:
        message: Current user message
        conversation_id: Optional conversation ID for loading history
        history: Optional pre-loaded list of LangChain messages (overrides conversation_id)
        memory_context: Optional pre-formatted memory text to prepend
    """
    # Build message list: memory_context → history → current message
    messages = []
    if memory_context:
        messages.append(HumanMessage(content=memory_context))
    if history is not None:
        messages.extend(history)
    else:
        messages.extend(_load_conversation_messages(conversation_id))
    messages.append(HumanMessage(content=message))

    initial_state = {
        "messages": messages,
        "original_question": message,
        "request_id": str(uuid.uuid4()),
        "thread_id": str(conversation_id or uuid.uuid4()),
    }

    result = agent.invoke(initial_state)

    final_message = result["messages"][-1]
    return normalize_answer(final_message.content)


def run_agent_with_reflexion(message: str, conversation_id: int | None = None,
                            history: list = None, memory_context: str = "") -> str:
    """Run Agent with Reflexion loop (v0.3)

    如果 Reflexion 循环未能产生合格回答，退化为普通 ReAct 回答。

    Args:
        message: Current user message
        conversation_id: Optional conversation ID for loading history
        history: Optional pre-loaded list of LangChain messages
        memory_context: Optional pre-formatted memory text to prepend
    """
    from agent.reflexion import reflexion_loop

    # Load history once, pass to both paths
    if history is not None:
        msg_history = list(history)
    else:
        msg_history = _load_conversation_messages(conversation_id)

    # 1. 尝试 Reflexion 循环
    result = reflexion_loop(message, history=msg_history,
                           memory_context=memory_context)

    if result:
        return normalize_answer(result)

    # 2. 降级：退化为普通 ReAct
    return run_agent(message, conversation_id, history=msg_history,
                     memory_context=memory_context)
