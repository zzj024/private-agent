# tools/knowledge_tools.py
# 职责：知识库检索工具——供 Agent 聊天时自动调用

import json
from dataclasses import dataclass
from typing import Literal

from langchain_ollama import ChatOllama

from rag.chroma_store import get_chroma_store
from config.settings import settings

EXCERPT_MAX_CHARS = 450

# LLM 实例（重排序用）
_rerank_llm = ChatOllama(model=settings.ollama_chat_model, temperature=0)


# ═══════════════════════════════════════════════
# 智能检索 A++ — QueryProfile
# ═══════════════════════════════════════════════

@dataclass
class QueryProfile:
    """查询配置档案——三种检索策略"""
    breadth: Literal["narrow", "normal", "broad"]
    probe_k: int
    rerank_soft_limit: int
    final_char_budget: int


PROFILES = {
    "narrow": QueryProfile("narrow", probe_k=10, rerank_soft_limit=6, final_char_budget=1800),
    "normal": QueryProfile("normal", probe_k=20, rerank_soft_limit=10, final_char_budget=3000),
    "broad": QueryProfile("broad", probe_k=30, rerank_soft_limit=15, final_char_budget=5000),
}

DEFAULT_PROFILE = PROFILES["normal"]


def assess_query_profile(query: str) -> QueryProfile:
    """
    基于关键词 + 长度判断查询的证据需求，不调 LLM。

    分类信号：
    - broad:  含"所有/总结/对比/分析/架构/演进/优缺点"等综合信号词
    - narrow: 含"是什么/在哪/多少/配置/路径"等单点信号词，且查询短
    - normal: 其余情况
    """
    q = query.strip()
    qlen = len(q)

    broad_keywords = [
        "所有", "总结", "对比", "分析", "梳理", "归纳", "关联",
        "方案", "架构", "演进", "优缺点", "风险", "取舍", "全部",
        "关系", "区别", "异同", "比较", "整理",
    ]

    narrow_keywords = [
        "是多少", "是什么", "在哪", "哪个", "多少", "电话",
        "邮箱", "路径", "配置", "key", "密码", "地址", "日期",
        "版本", "端口", "账号",
    ]

    has_broad = any(kw in q for kw in broad_keywords)
    has_narrow = any(kw in q for kw in narrow_keywords)
    is_short = qlen <= 15

    if has_broad:
        return PROFILES["broad"]
    if has_narrow and is_short:
        return PROFILES["narrow"]
    if is_short and not has_broad:
        return PROFILES["narrow"]
    return PROFILES["normal"]


def rule_prefilter(results: list[dict], profile: QueryProfile) -> list[dict]:
    """
    规则预筛：基于 distance gap 找到自然断点，截掉明显不相关的尾部。

    思路：
    - ChromaDB 按距离升序返回（越小越相关）
    - 如果某条和前一条的距离差突然变大（"断点"），说明从这里开始相关性陡降
    - 在断点处截断，保留前面的候选送入 LLM

    保底：
    - 结果 ≤ 2 条直接返回
    - 找不到明显断点时，取 soft_limit
    """

    if len(results) <= 2:
        return results

    # 提取距离
    distances = [r.get("distance") for r in results if r.get("distance") is not None]
    if len(distances) < 2:
        return results[:profile.rerank_soft_limit]

    limit = min(profile.rerank_soft_limit, len(distances))
    top1 = distances[0]

    # 计算相邻 gap，在 limit 窗口内找最大断点
    gaps = [distances[i + 1] - distances[i] for i in range(limit - 1)]

    # 用"相对于 top1 的倍数"判断 gap 是否显著
    # 实际距离量纲 ~1.0-1.2（768维 L2），典型 gap 0.01-0.04
    # 阈值 0.025 = 大概2-3倍于典型gap
    significant = [i for i, g in enumerate(gaps) if g / max(abs(top1), 1e-6) > 0.05]

    if significant:
        # 在第一个显著断点处截断，至少保留 2 条
        cut = significant[0] + 1
        return results[:max(cut, 2)]

    # 无明显断点 → 全保留（上限 soft_limit）
    return results[:limit]


def _parse_json_response(content: str) -> dict:
    """从 LLM 返回内容中提取 JSON，容错处理 markdown 包裹"""
    text = content.strip()

    # 剥掉 ```json ... ``` 包裹
    if text.startswith("```"):
        text = text.removeprefix("```").removeprefix("json").removesuffix("```").strip()

    # 找最外层花括号
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"No JSON in response: {content[:200]}")

    return json.loads(text[start:end + 1])


def _build_rerank_prompt(query: str, candidates: list[dict]) -> str:
    """构建 LLM 重排序 prompt，每条候选只给 excerpt（截断 450 字）"""
    blocks = []
    for i, c in enumerate(candidates, 1):
        source = c["metadata"].get("source", "")
        header = c["metadata"].get("header", "")
        document = c.get("document", "")

        excerpt = document[:EXCERPT_MAX_CHARS]
        if len(document) > EXCERPT_MAX_CHARS:
            excerpt += "..."

        blocks.append(
            f"[K{i}] distance={c['distance']:.4f} source={source}\n"
            f"header={header}\nexcerpt: {excerpt}"
        )

    return f"""你是私人知识库检索结果筛选器。

用户问题：
{query}

候选知识片段如下：
{chr(10).join(blocks)}

任务：
从候选片段中选择所有对回答用户问题有直接帮助的片段。

选择规则：
1. 只选择能提供具体事实、定义、设计细节、约束、例子或证据的片段。
2. 不要选择只是主题相近但没有实质帮助的片段。
3. 如果多个片段内容重复，只选择信息量最高的片段。
4. 如果问题需要综合、对比、总结或跨文档分析，可以选择多个互补片段。
5. 如果没有任何片段有帮助，返回空数组。
6. 不要为了凑数量而选择片段。
7. 复杂综合问题优先选择互补信息，不要只选择相似片段。

只返回 JSON，不要返回 Markdown，不要解释 JSON 之外的内容。

JSON 格式：
{{
  "selected": [
    {{
      "id": "K1",
      "relevance": 3,
      "reason": "简短说明为什么有帮助"
    }}
  ]
}}

relevance 取值：
3 = 直接回答问题，必须保留
2 = 有明显帮助，建议保留
1 = 弱相关，不要保留
0 = 无关，不要保留
"""


def llm_rerank_and_select(query: str, candidates: list[dict]) -> list[dict]:
    """单次 LLM 调用：relevance 打分 + 动态选择"""

    # 1. 构建 prompt，调 Qwen
    prompt = _build_rerank_prompt(query, candidates)
    response = _rerank_llm.invoke(prompt)
    content = response.content

    # 2. 从返回内容里解析出 JSON
    try:
        data = _parse_json_response(content)
    except ValueError:
        return candidates  # JSON 解析失败 → 降级，规则结果原样返回

    # 3. 建立编号 → 候选的映射
    by_label = {}
    for i, c in enumerate(candidates, 1):
        by_label[f"K{i}"] = c

    # 4. 只保留 relevance >= 2 的
    selected = []
    for item in data.get("selected", []):
        item_id = item.get("id", "")
        relevance = item.get("relevance", 0)
        if item_id in by_label and relevance >= 2:
            selected.append(by_label[item_id])

    # 5. 查空保护：LLM 返回空时保留前 2 条作为安全兜底
    #    避免 LLM 误判导致 Agent 完全丢失知识库上下文
    if not selected and len(candidates) >= 1:
        return candidates[:2]

    return selected


# ═══════════════════════════════════════════════
# 检索入口
# ═══════════════════════════════════════════════

def search_knowledge(query: str) -> str:
    """搜索私有知识库。使用智能检索 A++ 管线。"""
    return smart_search_knowledge(query)

def format_knowledge_results(results: list[dict], max_chars: int) -> str:
    if not results:
        return ""

    chunks = []
    total_chars = 0

    for i, item in enumerate(results, 1):
        doc = item["document"].strip()
        source = item["metadata"].get("source", "未知来源")
        header = item["metadata"].get("header", "")

        # 先算固定开销（编号 + 来源 + 标题），不算内容
        entry_header = f"[K{i}]\n来源：{source}"
        if header:
            entry_header += f"\n标题：{header}"

        # 剩余预算全给内容
        remaining = max_chars - total_chars - len(entry_header) - 20
        if remaining <= 0:
            break

        if len(doc) > remaining:
            doc = doc[:remaining] + "..."

        entry = f"{entry_header}\n内容：\n{doc}"
        chunks.append(entry)
        total_chars += len(entry)

    if not chunks:
        return ""

    return "以下是你的私有知识库检索结果：\n\n" + "\n\n".join(chunks)


def smart_search_knowledge(query: str) -> str:
    """智能检索主流程：自适应探头 + 规则预筛 + LLM 重排序 + 字符预算格式化"""

    # 0. 知识库不可用 → 直接空
    try:
        store = get_chroma_store()
    except Exception:
        return ""

    if store.count() == 0:
        return ""

    # ① LLM 判断查询复杂度（失败降级为 normal）
    profile = assess_query_profile(query)

    # 自适应探头
    raw_results = store.search(query,n_results=min(profile.probe_k, store.count()))
    if not raw_results:
        return ""

    # 规则预筛：gap 截断
    candidates = rule_prefilter(raw_results, profile)
    if not candidates:
        return ""

    # LLM 重排序（异常降级：跳过rerank，预筛结果直接格式化）
    try:
        selected = llm_rerank_and_select(query,candidates)
    except Exception:
        selected = candidates

    # LLM 也可能返回空（判断都不相关）
    if not selected:
        return ""

    # 按字符预算格式化
    return format_knowledge_results(selected,max_chars=profile.final_char_budget)