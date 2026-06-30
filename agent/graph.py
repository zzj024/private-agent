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


# ¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T
# Utility functions
# ¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T

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


# ¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T
# Build ReAct Agent
# ¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T

def build_agent():
    """Build ReAct Agent"""
    # Create LLM
    llm = ChatOllama(
        model=settings.ollama_chat_model,
        temperature=0,  # Reduce randomness, improve tool call accuracy
    )
    
    # Create ReAct Agent
    agent = create_react_agent(
        model=llm,
        tools=TOOLS,
        state_schema=AgentState,
    )
    
    return agent


# Build at module load time
agent = build_agent()


# ¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T
# Run entry point
# ¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T

def run_agent(message: str, conversation_id: int | None = None) -> str:
    """Run Agent"""
    # Build initial state
    initial_state = {
        "messages": [HumanMessage(content=message)],
        "original_question": message,
        "request_id": str(uuid.uuid4()),
        "thread_id": str(conversation_id or uuid.uuid4()),
    }
    
    # Run agent
    result = agent.invoke(initial_state)
    
    # Extract final answer
    final_message = result["messages"][-1]
    return normalize_answer(final_message.content)
