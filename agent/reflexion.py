from dataclasses import dataclass
from typing import List, Optional
import contextvars
import json
import re

from config.settings import settings


# ═══════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════

@dataclass
class ReviewResult:
    """审核结果（结构化）"""
    score: int              # 1-10 分
    passed: bool            # score >= pass_score 算通过
    issues: List[str]       # 发现的问题
    suggestions: List[str]  # 改进建议


@dataclass
class ReflexionAttempt:
    """一次 Reflexion 循环的尝试"""
    attempt: int            # 第几次尝试
    answer: str             # Agent 的回答
    review: ReviewResult    # 审核结果（结构化）
    cached_data: dict       # 缓存的数据


# ═══════════════════════════════════════════════
# ReflexionState
# ═══════════════════════════════════════════════

class ReflexionState:
    """Reflexion 循环状态"""

    def __init__(self):
        self.attempts: List[ReflexionAttempt] = []  # 所有尝试记录
        self.data_cache: dict = {}  # 工具层数据缓存（仅存原始数据）
        self.question: str = ""  # 原始问题

    def _normalize_key(self, query: str) -> str:
        """缓存 key 标准化归一化（去首尾空格、合并中间连续空白、全小写）"""
        return " ".join(query.split()).lower()

    def cache_tool_result(self, tool_name: str, query: str, result: str):
        """缓存工具调用结果（原始数据，非 LLM 答案）"""
        key = f"{tool_name}:{self._normalize_key(query)}"
        self.data_cache[key] = result

    def get_cached_tool_result(self, tool_name: str, query: str) -> Optional[str]:
        """获取缓存的工具调用结果"""
        key = f"{tool_name}:{self._normalize_key(query)}"
        return self.data_cache.get(key)

    def clear_cache(self, prefix: str = ""):
        """清除缓存（prefix 为空则清除全部，如 'memory:' 清除所有记忆相关缓存）"""
        if not prefix:
            self.data_cache.clear()
        else:
            keys_to_delete = [k for k in self.data_cache if k.startswith(prefix)]
            for k in keys_to_delete:
                del self.data_cache[k]

    def add_attempt(self, attempt: ReflexionAttempt):
        """添加一次尝试"""
        self.attempts.append(attempt)

    def get_best_attempt(self) -> Optional[ReflexionAttempt]:
        """获取得分最高的尝试（无论分数高低）"""
        if not self.attempts:
            return None
        return max(self.attempts, key=lambda x: x.review.score)

    def should_terminate_early(self) -> bool:
        """判断是否应该提前终止（连续两次分数没有提升）"""
        if len(self.attempts) < 2:
            return False
        return self.attempts[-1].review.score <= self.attempts[-2].review.score


# ═══════════════════════════════════════════════
# Context 变量（用于传递 state 给工具函数）
# ═══════════════════════════════════════════════

_reflexion_state: contextvars.ContextVar[Optional[ReflexionState]] = contextvars.ContextVar(
    'reflexion_state', default=None
)


def set_current_state(state: Optional[ReflexionState]):
    """设置当前 ReflexionState"""
    _reflexion_state.set(state)


def get_current_state() -> Optional[ReflexionState]:
    """获取当前 ReflexionState"""
    return _reflexion_state.get()


# ═══════════════════════════════════════════════
# 核心函数
# ═══════════════════════════════════════════════

def generate_answer(question: str, history: list = None,
                   memory_context: str = "") -> str:
    """Agent 生成答案（不缓存答案，每轮都重新调用）"""
    from agent.graph import run_agent
    return run_agent(question, history=history,
                     memory_context=memory_context)


def _extract_json(text: str) -> Optional[dict]:
    """从文本中提取 JSON（容错处理）"""
    if not text or not isinstance(text, str):
        return None
    # 尝试直接解析
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    # 尝试提取 ```json ... ``` 代码块
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    # 尝试提取 { ... } 最外层（非贪婪）
    match = re.search(r'\{.*?\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return None


def review_answer(question: str, answer: str) -> ReviewResult:
    """审核员检查（DeepSeek）"""
    prompt = f"""你是一个严格的代码审核员。请评估以下回答的质量。

检查项目：
1. 语法正确性（代码是否能运行）
2. 逻辑完整性（是否回答了用户问题）
3. 格式规范（Markdown 格式是否正确）
4. 引用准确（知识库引用是否正确）

请严格只返回 JSON，不要包含其他文字：
{{
    "score": 8,
    "passed": true,
    "issues": ["问题1", "问题2"],
    "suggestions": ["建议1", "建议2"]
}}

用户问题：{question}
Agent 回答：{answer}
"""

    try:
        from llm.deepseek_client import get_deepseek_client
        client = get_deepseek_client()
        response = client.chat(prompt)
        result = _extract_json(response)

        if result is None:
            # JSON 解析失败，返回默认低分
            return ReviewResult(
                score=3,
                passed=False,
                issues=["审核系统无法解析 DeepSeek 返回结果"],
                suggestions=["请简化回答格式"]
            )

        return ReviewResult(
            score=result.get("score", 5),
            passed=result.get("passed", False),
            issues=result.get("issues", []),
            suggestions=result.get("suggestions", [])
        )
    except Exception as e:
        # DeepSeek 调用失败，返回默认低分
        return ReviewResult(
            score=3,
            passed=False,
            issues=[f"审核服务异常: {str(e)}"],
            suggestions=["请稍后重试"]
        )


def reflexion_loop(question: str, max_retries: int = None,
                  history: list = None, memory_context: str = "") -> Optional[str]:
    """Reflexion 循环"""
    if max_retries is None:
        max_retries = settings.reflexion_max_retries

    # 1. 初始化状态
    state = ReflexionState()
    state.question = question
    state.history = history or []
    state.memory_context = memory_context

    # 2. 设置当前 state（供工具函数通过 get_current_state() 获取）
    set_current_state(state)

    try:
        # 3. 循环开始
        feedback = ""  # 反馈与原始问题分离

        for i in range(max_retries):
            # 4. Agent 生成答案
            if feedback:
                # 将反馈附加上去，但不污染原始问题
                full_question = f"{state.question}\n\n[审核反馈] {feedback}"
            else:
                full_question = state.question

            answer = generate_answer(full_question, history=state.history,
                                     memory_context=state.memory_context)

            # 5. 审核员检查
            review = review_answer(state.question, answer)

            # 6. 记录这次尝试
            attempt = ReflexionAttempt(
                attempt=i + 1,
                answer=answer,
                review=review,
                cached_data=state.data_cache.copy()
            )
            state.add_attempt(attempt)

            # 7. 检查是否通过
            if review.passed:
                return answer

            # 8. 智能终止：连续两次分数没有提升
            if state.should_terminate_early():
                break

            # 9. 构建下一轮反馈（不覆盖原始问题）
            issues_text = "；".join(review.issues) if review.issues else "无具体问题"
            suggestions_text = "；".join(review.suggestions) if review.suggestions else "无具体建议"
            feedback = f"问题：{issues_text}。建议：{suggestions_text}"

        # 10. 循环结束，返回得分最高的回答
        best_attempt = state.get_best_attempt()
        if best_attempt and best_attempt.review.score >= settings.reflexion_min_score:
            return best_attempt.answer

        # 11. 所有尝试都不合格
        return None

    finally:
        # 12. 清除当前 state
        set_current_state(None)
