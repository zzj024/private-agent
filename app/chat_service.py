# app/chat_service.py
# 职责：统一聊天服务——/chat 和 /chat/stream 都调这个类

import json
import uuid
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage

# 使用模块级单例，避免重复 build_agent()
from agent.graph import agent


class ChatService:
    """统一聊天服务——/chat 和 /chat/stream 共用"""

    def __init__(self):
        self.graph = agent

    async def stream_events(
        self,
        message: str,
        conversation_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        核心方法：统一的异步事件流。
        
        - /chat 端点的同步 handler 会遍历这个 generator，收集最终结果后返回 JSON
        - /chat/stream 端点的 SSE handler 会逐条推送这个 generator 的事件
        
        产出的每个事件都是 JSON 字符串，格式：{"event": "...", "data": {...}}
        """
        # 1. 准备请求上下文
        request_id = str(uuid.uuid4())
        thread_id = conversation_id or str(uuid.uuid4())

        # 2. 推送 meta 事件（告知前端基本上下文）
        yield self._make_event("meta", {
            "request_id": request_id,
            "thread_id": thread_id,
        })

        # 3. 构建 LangGraph 输入
        config = {
            "configurable": {"thread_id": thread_id},
        }
        input_data = {
            "messages": [HumanMessage(content=message)],
            "original_question": message,
            "thread_id": thread_id,
            "request_id": request_id,
        }

        # 4. 启动 graph.astream_events
        #    使用 version="v2" 获取新版事件格式
        try:
            async for event in self.graph.astream_events(
                input_data,
                config=config,
                version="v2",
            ):
                converted = self._convert_langgraph_event(event)
                if converted:
                    yield converted
        except Exception as e:
            yield self._make_event("error", {
                "code": "AGENT_ERROR",
                "message": str(e),
                "retryable": True,
            })

        # 5. 推送 done 事件
        yield self._make_event("done", {
            "request_id": request_id,
        })

    def _make_event(self, event_type: str, data: dict) -> str:
        """把事件类型和数据打包成 JSON 字符串"""
        return json.dumps({"event": event_type, "data": data}, ensure_ascii=False)

    def _convert_langgraph_event(self, event: dict) -> str | None:
        """
        把 LangGraph 的 astream_events 原生事件
        转换成我们自定义的 SSE 事件格式
        
        事件映射：
        - on_chain_start → stage（节点开始）
        - on_chain_end → final（最终结果）
        - on_tool_start → stage（工具开始）
        - on_tool_end → stage（工具结束）
        - on_chain_error → error（错误）
        """
        kind = event.get("event", "")

        # 节点开始运行 → 转成 stage 事件
        if kind == "on_chain_start":
            node_name = event.get("name", "")
            stage_map = {
                "agent": ("正在思考...", "分析你的问题，决定调用哪些工具"),
                "tools": ("正在执行工具...", "调用知识库或记忆系统"),
                "chat": ("正在生成回答...", "结合记忆和知识库回答问题"),
                "save_memory": ("正在保存记忆...", "将信息存入长期记忆"),
                "delete_memory": ("正在删除记忆...", ""),
                "list_memories": ("正在查询记忆...", ""),
                "search_knowledge": ("正在检索知识库...", "查找相关文档"),
            }
            stage_info = stage_map.get(node_name, (f"正在执行: {node_name}", ""))
            return self._make_event("stage", {
                "stage": stage_info[0],
                "message": stage_info[1],
            })

        # 工具开始执行 → 转成 stage 事件
        elif kind == "on_tool_start":
            tool_name = event.get("name", "")
            tool_input = event.get("data", {}).get("input", {})
            
            # 根据工具类型显示不同提示
            if tool_name == "save_memory":
                key = tool_input.get("key", "")
                return self._make_event("stage", {
                    "stage": f"正在保存记忆: {key}",
                    "message": "将信息存入长期记忆",
                })
            elif tool_name == "search_knowledge":
                query = tool_input.get("query", "")
                return self._make_event("stage", {
                    "stage": f"正在检索: {query}",
                    "message": "查找相关文档",
                })
            elif tool_name == "delete_memory":
                key = tool_input.get("key", "")
                return self._make_event("stage", {
                    "stage": f"正在删除记忆: {key}",
                    "message": "",
                })
            else:
                return self._make_event("stage", {
                    "stage": f"正在执行: {tool_name}",
                    "message": "",
                })

        # 工具执行完成 → 转成 stage 事件
        elif kind == "on_tool_end":
            tool_name = event.get("name", "")
            return self._make_event("stage", {
                "stage": f"完成: {tool_name}",
                "message": "",
            })

        # 节点执行完毕 → 检查是否是最终答案
        elif kind == "on_chain_end":
            output = event.get("data", {}).get("output", {})
            if isinstance(output, dict):
                # ReAct Agent 的最终答案在 messages 的最后一条
                messages = output.get("messages", [])
                if messages:
                    last_message = messages[-1]
                    if hasattr(last_message, "content"):
                        content = last_message.content
                        # 检查是否有 tool_calls（如果有，说明还在循环中）
                        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                            return None  # 还有工具要调用，不是最终答案
                        if content:
                            return self._make_event("final", {
                                "content": content,
                                "citations": [],
                            })
                # 兼容旧格式
                final = output.get("final_answer") or output.get("response")
                if final:
                    return self._make_event("final", {
                        "content": final,
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
        return None