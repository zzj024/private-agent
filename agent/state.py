# agent/state.py
# 职责：定义 LangGraph 工作流中节点间传递的状态结构

from typing import Optional, TypedDict


class AgentState(TypedDict):
    """LangGraph 的 State——所有节点共享的数据容器"""
    message: str                    # 用户输入的消息
    conversation_id: Optional[int]  # 会话 ID
    intent: str                     # 识别到的意图（detect_intent 填写）
    extracted_key: str              # 从"记住"中提取的 key
    extracted_value: str            # 从"记住"中提取的 value
    extracted_category: str         # 从"记住"中提取的分类
    response: str                   # 最终回答
