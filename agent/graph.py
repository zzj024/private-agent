# agent/graph.py
# Responsibility: LangGraph workflow - ReAct loop (Reasoning-Action-Observation)

import uuid
import re
from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

from agent.state import AgentState
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
    """Build ReAct Agent"""
    llm = ChatOllama(
        model=settings.ollama_chat_model,
        temperature=0,  # Reduce randomness, improve tool call accuracy
    )

    agent = create_react_agent(
        model=llm,
        tools=TOOLS,
        state_schema=AgentState,
    )

    return agent


# Build at module load time
agent = build_agent()


# ═══════════════════════════════════════════════
# Run entry points
# ═══════════════════════════════════════════════

def run_agent(message: str, conversation_id: int | None = None) -> str:
    """Run Agent (v0.2 ReAct)"""
    initial_state = {
        "messages": [HumanMessage(content=message)],
        "original_question": message,
        "request_id": str(uuid.uuid4()),
        "thread_id": str(conversation_id or uuid.uuid4()),
    }

    result = agent.invoke(initial_state)

    final_message = result["messages"][-1]
    return normalize_answer(final_message.content)


def run_agent_with_reflexion(message: str, conversation_id: int | None = None) -> str:
    """Run Agent with Reflexion loop (v0.3)

    如果 Reflexion 循环未能产生合格回答，退化为普通 ReAct 回答。
    """
    from agent.reflexion import reflexion_loop

    # 1. 尝试 Reflexion 循环
    result = reflexion_loop(message)

    if result:
        return normalize_answer(result)

    # 2. 降级：退化为普通 ReAct
    return run_agent(message, conversation_id)
