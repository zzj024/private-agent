# agent/state.py
# Responsibility: Define v0.2 GraphState - shared data container for all nodes

from typing import TypedDict, Optional


class GraphState(TypedDict, total=False):
    """v0.2 Graph State - only contains fields actually used in current phase
    
    Field description:
        request_id: str           Request tracking ID
        thread_id: str            LangGraph thread ID
        messages: list            Conversation message list (inherited from MessagesState)
        original_question: str    User original question
        pending_tool_calls: list  Qwen bind_tools output tool_call list
        tool_results: list        Tool execution results list
        requires_confirmation: bool  Destructive operation needs confirmation
        final_answer: str         Final answer
        stage: str                Running stage (analysis/retrieval/generation etc.)
        attempt: int              Current attempt count
        errors: list              Error list
        remaining_steps: int      Remaining steps for ReAct loop
        
    Phase 1 compatible fields (removed after Phase 2 uses tool calling):
        message: str              User message (compatible with old code)
        conversation_id: int      Conversation ID (compatible with old code)
        intent: str               Intent type (removed in Phase 2)
        extracted_key: str        Extracted key (removed in Phase 2)
        extracted_value: str      Extracted value (removed in Phase 2)
        response: str             Response content (compatible with old code, changed to final_answer in Phase 2)
    """
    # === v0.2 Core fields ===
    request_id: str
    thread_id: str
    messages: list
    original_question: str
    pending_tool_calls: list[dict]
    tool_results: list[dict]
    requires_confirmation: bool
    final_answer: str
    stage: str
    attempt: int
    errors: list[dict]
    remaining_steps: int
    is_last_step: bool      # LangGraph managed: True when remaining_steps <= 1
    
    # === Phase 1 compatible fields (removed in Phase 2) ===
    message: str
    conversation_id: Optional[int]
    intent: str
    extracted_key: str
    extracted_value: str
    response: str


# Backward compatibility: keep old AgentState type alias
AgentState = GraphState
