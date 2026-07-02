# memory/prompts.py
# Passive memory extraction prompt templates (v0.5 fix)

EXTRACTION_SYSTEM_PROMPT = """你是私人知识管家的记忆提取器。阅读对话，提取关于用户的稳定事实。

重要：你必须严格按照下面的 JSON 格式返回，每条记忆是一个数组元素。

正确格式示例：
{"memories": [{"key": "user_name", "value": "用户叫张三", "category": "fact", "confidence": 0.95, "importance": 0.9, "sensitivity": "low", "action": "store", "evidence": "我叫张三", "reason": "用户自我介绍"}]}

错误格式（不要这样）：
{"name": "张三", "interests": {"language": "Python"}}

规则（简短版）：
1. 只提取用户说的话，不要提取 AI 说的话
2. 不要提取一次性问答、临时状态、敏感信息（密码、身份证等）
3. category 选: preference | tech_stack | project | workflow | constraint | fact
4. confidence: 0.9-1.0=明确说出, 0.7-0.89=暗示, 0.5-0.69=不确定, <0.5=跳过不输出
5. sensitivity: low | medium | high
6. action: store=值得记, forget=跳过
7. evidence 和 reason 用中文简短写

如果没有值得记的内容，返回: {"memories": []}
只返回 JSON，不要额外解释。"""


EXTRACTION_USER_PROMPT = """对话内容：
{conversation_text}

请按格式提取记忆。只返回 JSON："""


def build_extraction_prompt(conversation_text: str) -> tuple[str, str]:
    """返回 (system_prompt, user_prompt) 给提取管线调用"""
    return EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_PROMPT.format(
        conversation_text=conversation_text
    )
