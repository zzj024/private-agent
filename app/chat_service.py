from dataclasses import dataclass, asdict
from typing import Optional

import json
import uuid
from typing import AsyncGenerator
from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage

from agent.graph import build_agent
from agent.state import AgentState

@dataclass
class SSEMeta:
    """连接建立时推送，包含这次请求的基本信息"""
    request_id: str
    conversation_id: str

@dataclass 
class SSEStage:
    """阶段更新，告诉前端 agent 正在干什么"""
    stage: str          # 如 "正在分析问题..." / "正在检索知识库..."
    message: str        # 详细描述

@dataclass
class SSEDelta:
    """流式文本块，按顺序拼接就是完整答案"""
    seq: int            # 序号，前端按此顺序拼接
    content: str        # 文本片段

@dataclass
class SSEFinal:
    """最终答案，包含完整内容和引用信息"""
    content: str
    citations: list[str]  # 引用的知识库来源

@dataclass
class SSEError:
    """错误事件"""
    code: str           # 错误码
    message: str        # 人类可读的错误描述
    retryable: bool     # 前端是否可以自动重试

@dataclass  
class SSEDone:
    """消息结束"""
    request_id: str

class ChatService:
    """统一聊天服务——/chat 和 /chat/stream 都调这个类"""

    def __init__(self):
        # build_agent() 是你现有的 graph builder
        # MemorySaver 让 LangGraph 记住对话状态（支持 checkpoint）
        self.graph: StateGraph = build_agent()
        self.checkpointer = MemorySaver()

    async def stream_events(
        self,
        message: str,
        conversation_id: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        核心方法：统一的异步事件流。
        
        - /chat 端点的同步 handler 会遍历这个 generator，收集最终结果后返回 JSON
        - /chat/stream 端点的 SSE handler 会逐条推送这个 generator 的事件
        
        产出的每个事件都是 JSON 字符串，格式：{"event": "...", "data": {...}}
        """
        # 1. 准备请求上下文
        request_id = str(uuid.uuid4())
        thread_id = str(conversation_id or uuid.uuid4())

        # 2. 推送 meta 事件（告知前端基本上下文）
        yield self._make_event("meta", {
            "request_id": request_id,
            "conversation_id": thread_id,
        })

        # 3. 构建 LangGraph 输入
        config = {
            "configurable": {"thread_id": thread_id},
        }
        input_data = {
            "messages": [HumanMessage(content=message)],
            "original_question": message,
            "request_id": request_id,
        }

        # 4. 启动 graph.astream_events
        #    astream_events 是 LangGraph v0.2+ 的异步事件流 API
        #    version="v2" 表示用新版事件格式
        try:
            async for event in self.graph.astream_events(
                input_data,
                config=config,
                version="v2",
            ):
                yield self._convert_langgraph_event(event)
        except Exception as e:
            yield self._make_event("error", {
                "code": "AGENT_ERROR",
                "message": str(e),
                "retryable": True,
            })
    def _make_event(self, event_type: str, data: dict) -> str:
        """把事件类型和数据打包成 JSON 字符串"""
        return json.dumps({"event": event_type, "data": data}, ensure_ascii=False)

    def _convert_langgraph_event(self, event: dict) -> str:
        """
        把 LangGraph 的 astream_events 原生事件
        转换成我们自定义的 SSE 事件格式
        
        LangGraph 原生事件格式：
        {"event": "on_chat_model_stream", "data": {"chunk": ...}}
        {"event": "on_chain_start", "data": {"input": ...}}
        {"event": "on_chain_end", "data": {"output": ...}}
        """
        kind = event.get("event", "")

        # 节点开始运行 → 转成 stage 事件
        if kind == "on_chain_start":
            node_name = event.get("name", "")
            stage_map = {
                "detect_intent": ("正在分析意图...", "判断你要做什么操作"),
                "chat": ("正在检索知识库并生成回答...", "结合你的记忆和知识库回答问题"),
                "save_memory": ("正在保存记忆...", "将信息存入长期记忆"),
                "delete_memory": ("正在删除记忆...", ""),
                "list_memories": ("正在查询记忆...", ""),
            }
            stage_info = stage_map.get(node_name, (f"正在执行: {node_name}", ""))
            return self._make_event("stage", {
                "stage": stage_info[0],
                "message": stage_info[1],
            })

        # LLM 流式输出 → 转成 delta 事件
        elif kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk", {})
            content = chunk.get("content", "")
            if content:
                return self._make_event("delta", {
                    "seq": id(self),  # 简化处理，实际应该用计数器
                    "content": content,
                })

        # 节点执行完毕 → 检查是否是最终答案
        elif kind == "on_chain_end":
            output = event.get("data", {}).get("output", {})
            if isinstance(output, dict) and output.get("response"):
                return self._make_event("final", {
                    "content": output["response"],
                    "citations": [],
                })

        # 遇到错误 → 转成 error 事件
        elif kind == "on_chain_error":
            error = event.get("data", {}).get("error", str(event))
            return self._make_event("error", {
                "code": "AGENT_ERROR",
                "message": str(error),
                "retryable": True,
            })

        # 其他事件类型忽略
        return ""