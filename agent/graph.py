# agent/graph.py
# 职责：LangGraph 工作流——意图判断 + 路由 + 执行

import re
import json
from langgraph.graph import StateGraph, END

from agent.state import AgentState
from agent.prompts import SYSTEM_PROMPT, KNOWLEDGE_POLICY, DETECT_PROMPT
from memory.sqlite_store import get_store
from llm.ollama_client import get_ollama_client
from tools.knowledge_tools import search_knowledge


# ═══════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════

def normalize_answer(text: str) -> str:
    """统一处理 LLM 回答的 Markdown 格式"""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").strip()
    # 编号列表前补空行
    text = re.sub(r"([^\n])\n(?=\d+[.、]\s+)", r"\1\n\n", text)
    # 去掉过多空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ═══════════════════════════════════════════════
# 规则优先意图判断
# ═══════════════════════════════════════════════

QUESTION_PATTERNS = [
    r"怎么", r"如何", r"为什么", r"怎么办",
    r"怎么解决", r"能不能", r"是不是", r"是否",
    r"吗[？?]?$", r"[？?]$", r"帮我分析",
    r"解释一下", r"讲讲", r"方案", r"原因",
]

REMEMBER_PATTERNS = [
    r"记住", r"记一下", r"帮我记",
]

LIST_PATTERNS = [
    r"查看记忆", r"我的记忆", r"^list$", r"^ls$",
]


def rule_detect_intent(text: str) -> str | None:
    """规则优先判断意图，匹配到直接返回，不走 LLM"""
    text = text.strip()

    # 查看记忆最优先
    if any(re.search(p, text) for p in LIST_PATTERNS):
        return "list"

    # 疑问句 → chat
    if any(re.search(p, text) for p in QUESTION_PATTERNS):
        return "chat"

    # 明确记忆指令 → remember
    if any(re.search(p, text) for p in REMEMBER_PATTERNS):
        return "remember"

    return None


def llm_detect_intent(text: str) -> str:
    """LLM 兜底判断意图"""
    llm = get_ollama_client()
    prompt = DETECT_PROMPT.replace("{message}", text)
    reply = llm.chat("qwen2.5:7b", [{"role": "user", "content": prompt}])

    # 提取 JSON
    cleaned = reply.strip()
    if "```" in cleaned:
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        result = json.loads(cleaned)
        intent = result.get("intent", "chat")
        return intent
    except json.JSONDecodeError:
        return "chat"


def detect_intent(text: str) -> dict:
    """总入口：规则优先 → LLM 兜底"""
    # 规则优先
    rule_result = rule_detect_intent(text)
    if rule_result:
        return {"intent": rule_result}

    # LLM 兜底
    intent = llm_detect_intent(text)

    if intent == "remember":
        # 用 LLM 提取 key/value
        llm = get_ollama_client()
        extract_prompt = f"""从以下文本中提取要记住的信息。
返回 JSON：{{"key": "主题", "value": "具体内容"}}

文本：{text}"""
        reply = llm.chat("qwen2.5:7b", [{"role": "user", "content": extract_prompt}])
        try:
            result = json.loads(reply.strip())
            return {
                "intent": "remember",
                "extracted_key": result.get("key", "note"),
                "extracted_value": result.get("value", text),
            }
        except json.JSONDecodeError:
            return {"intent": "remember", "extracted_key": "note", "extracted_value": text}

    return {"intent": "chat"}


# ═══════════════════════════════════════════════
# Node 1：意图判断
# ═══════════════════════════════════════════════

def detect_intent_node(state: AgentState) -> dict:
    """判断用户意图"""
    msg = state["message"].strip()
    result = detect_intent(msg)

    if result["intent"] == "remember":
        return {
            "intent": "remember",
            "extracted_key": result.get("extracted_key", ""),
            "extracted_value": result.get("extracted_value", ""),
        }
    return {"intent": result["intent"]}


# ═══════════════════════════════════════════════
# 条件路由
# ═══════════════════════════════════════════════

def route_intent(state: AgentState) -> str:
    return state["intent"]


# ═══════════════════════════════════════════════
# Node 2：保存记忆
# ═══════════════════════════════════════════════

def save_memory(state: AgentState) -> dict:
    store = get_store()
    key = state.get("extracted_key", "") or "note"
    value = state.get("extracted_value", "") or state["message"]
    store.save_memory(key, value, category="preference")
    return {"response": f"已记住：{key} = {value}"}


# ═══════════════════════════════════════════════
# Node 3：列出记忆
# ═══════════════════════════════════════════════

def list_memories(state: AgentState) -> dict:
    store = get_store()
    memories = store.list_memories()
    if not memories:
        return {"response": "目前还没有保存任何记忆。"}
    lines = ["你的长期记忆："]
    for m in memories:
        lines.append(f"- {m['key']}: {m['value']}（{m['category']}）")
    return {"response": "\n".join(lines)}


# ═══════════════════════════════════════════════
# Node 4：聊天（带知识库检索）
# ═══════════════════════════════════════════════

def chat(state: AgentState) -> dict:
    store = get_store()
    llm = get_ollama_client()
    user_msg = state["message"]

    # 检索知识库
    knowledge = search_knowledge(user_msg)

    # 构建消息
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # 长期记忆
    memories = store.list_memories()
    mem_parts = [f"- {m['key']}: {m['value']}" for m in memories]
    if mem_parts:
        context = "关于用户我知道以下信息：\n" + "\n".join(mem_parts)
        messages.append({"role": "system", "content": context})

    # 知识库策略
    messages.append({"role": "system", "content": KNOWLEDGE_POLICY})

    # 用户消息 + 知识库上下文放在一起
    knowledge_block = knowledge if knowledge else "（知识库无相关内容）"
    user_content = f"""用户问题：
{user_msg}

<knowledge_context>
{knowledge_block}
</knowledge_context>

回答要求：
- 如果 <knowledge_context> 中有相关内容，优先依据它回答。
- 如果 <knowledge_context> 为空或明显无关，先说明知识库没有相关内容，再给出通用建议。
- 不要忽略 <knowledge_context>。"""
    messages.append({"role": "user", "content": user_content})

    reply = llm.chat("qwen2.5:7b", messages)
    reply = normalize_answer(reply)
    return {"response": reply}


# ═══════════════════════════════════════════════
# 构建工作流图
# ═══════════════════════════════════════════════

def build_agent() -> StateGraph:
    workflow = StateGraph(AgentState)

    workflow.add_node("detect_intent", detect_intent_node)
    workflow.add_node("save_memory", save_memory)
    workflow.add_node("list_memories", list_memories)
    workflow.add_node("chat", chat)

    workflow.set_entry_point("detect_intent")

    workflow.add_conditional_edges(
        "detect_intent",
        route_intent,
        {
            "remember": "save_memory",
            "list": "list_memories",
            "chat": "chat",
        },
    )

    workflow.add_edge("save_memory", END)
    workflow.add_edge("list_memories", END)
    workflow.add_edge("chat", END)

    return workflow.compile()


agent = build_agent()


def run_agent(message: str, conversation_id: int | None = None) -> str:
    result = agent.invoke({
        "message": message,
        "conversation_id": conversation_id,
        "intent": "",
        "extracted_key": "",
        "extracted_value": "",
        "response": "",
    })
    return result["response"]
