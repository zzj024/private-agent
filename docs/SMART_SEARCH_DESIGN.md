# 智能检索实施方案 A++（v0.3 P2）

> 版本：v2.0
> 日期：2026-07-01
> 状态：待实施
> 前身：A+（已废弃）— 参见 git log `110d346`

---

## 一、设计变更说明

### A+ 方案为什么被推翻

A+ 方案的目标管线：

```
ChromaDB Top-20 → 规则剪枝(5-8条) → LLM 重排序(1-5条) → 返回
```

存在四个设计缺陷：

| # | 缺陷 | 影响 |
|---|------|------|
| 1 | `PROBE_N=20` 固定 | 简单问题浪费，复杂问题可能召回不足 |
| 2 | `MAX_FINAL_RESULTS=5` 固定 | 压制综合问题需要多证据的场景 |
| 3 | LLM 被迫"选 1-5 条" | 不允许 0 条（无相关内容），也不允许 8/10/12 条 |
| 4 | 规则剪枝只裁数量不判证据 | 优化的是"候选数量"而非"证据充分性" |

### A++ 核心思想

> 不是固定返回 Top-K，而是在上下文预算内返回所有真正有证据价值的知识片段。

```
A+: ChromaDB Top-20 → 规则剪枝 5-8 → LLM 选 1-5 → 返回
A++: 查询 Profile → 自适应探头 → 规则预筛 → LLM 动态选择 → 字符预算格式化
```

**一句话：自适应探头 + 允许 0 条 + 不固定 1-5 条 + 语义动态选择 + 工程预算上限**

---

## 二、核心设计决策

| 决策 | 结论 | 原因 |
|------|------|------|
| 探头数 | **按查询 profile 动态化** | narrow 10 / normal 20 / broad 30，规则判断，0 额外 LLM |
| 返回上限 | **从条数上限改为字符预算** | 1800 / 3000 / 5000 字符，不让"5条"压制复杂查询 |
| 空结果 | **允许** | LLM 可判断"都不相关"返回空，但有 top1 强相关的查空保护 |
| LLM 重排序 | **加 relevance 分数** | 0-3 分，代码只保留 ≥2 的；防止 Qwen "多多益善"偏向 |
| LLM 调用次数 | **1 次**（保留） | 只在重排序环节调 LLM，profile 评估用规则 |
| 规则预筛 | **三信号联合判断** | top1 优势 + 簇稳定性 + gap 检测，不再只看 gap_1_to_5 |
| 签名 | **不变**（保留） | `search_knowledge(query: str) -> str` |
| 可关闭 | **是**（保留） | `KNOWLEDGE_RERANK_ENABLED=false` 回退到规则 |
| 缓存兼容 | **是**（保留） | cache key 加 `smart_v2` 版本前缀 |
| 独立 search agent | **不做**（保留） | 96 chunks 规模不需要，留给 v0.4 |

---

## 三、QueryProfile 与配置

### 3.1 三级 Profile

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class QueryProfile:
    breadth: Literal["narrow", "normal", "broad"]
    probe_k: int
    rerank_soft_limit: int
    final_char_budget: int
```

| Profile | 场景 | probe_k | rerank 候选上限 | 最终字符预算 |
|---------|------|---------|----------------|-------------|
| **narrow** | 单点事实查询（是什么/在哪/配置值） | 10 | 6 | 1800 |
| **normal** | 普通解释/流程说明 | 20 | 10 | 3000 |
| **broad** | 综合/对比/分析/所有 | 30 | 15 | 5000 |

### 3.2 评估规则（纯规则，不调 LLM）

```python
def assess_query_profile(query: str) -> QueryProfile:
    """基于关键词 + 长度判断证据需求，不调 LLM"""

    q = query.strip()
    qlen = len(q)

    # 综合/多证据信号词
    broad_keywords = [
        "所有", "总结", "对比", "分析", "梳理", "归纳", "关联",
        "方案", "架构", "演进", "优缺点", "风险", "取舍", "全部",
        "关系", "区别", "异同", "比较", "整理",
    ]

    # 单点信号词
    narrow_keywords = [
        "是多少", "是什么", "在哪", "哪个", "多少", "电话",
        "邮箱", "路径", "配置", "key", "密码", "地址", "日期",
        "版本", "端口", "账号",
    ]

    has_broad = any(kw in q for kw in broad_keywords)
    has_narrow = any(kw in q for kw in narrow_keywords)
    is_long = qlen > 40

    # broad 优先：含综合信号词 → broad
    if has_broad:
        return QueryProfile("broad", probe_k=30, rerank_soft_limit=15, final_char_budget=5000)

    # narrow：含单点信号词 + 短 + 无综合信号
    if has_narrow and not is_long:
        return QueryProfile("narrow", probe_k=10, rerank_soft_limit=6, final_char_budget=1800)

    # narrow：短且无综合信号
    if qlen <= 15 and not has_broad:
        return QueryProfile("narrow", probe_k=10, rerank_soft_limit=6, final_char_budget=1800)

    # 默认 normal
    return QueryProfile("normal", probe_k=20, rerank_soft_limit=10, final_char_budget=3000)
```

### 3.3 配置项（.env）

```env
# 智能检索 A++ — probe
KNOWLEDGE_PROBE_NARROW=10
KNOWLEDGE_PROBE_NORMAL=20
KNOWLEDGE_PROBE_BROAD=30

# 智能检索 A++ — rerank 候选
KNOWLEDGE_RERANK_LIMIT_NARROW=6
KNOWLEDGE_RERANK_LIMIT_NORMAL=10
KNOWLEDGE_RERANK_LIMIT_BROAD=15

# 智能检索 A++ — 最终字符预算
KNOWLEDGE_CHARS_NARROW=1800
KNOWLEDGE_CHARS_NORMAL=3000
KNOWLEDGE_CHARS_BROAD=5000

# 智能检索 A++ — 总开关
KNOWLEDGE_RERANK_ENABLED=true
KNOWLEDGE_ALLOW_EMPTY_RESULTS=true
```

---

## 四、数据流

```
search_knowledge(query)
  │
  ├─ 1. assess_query_profile(query)
  │      → narrow / normal / broad
  │      → 确定 probe_k, rerank_soft_limit, final_char_budget
  │
  ├─ 2. ChromaDB.search(query, n_results=probe_k)
  │      → 结果含 distance
  │
  ├─ 3. rule_prefilter(results, profile)
  │      → 三信号: top1 优势 + 簇稳定性 + gap 检测
  │      → 不硬裁 5/6/8，在 soft_limit 内找自然断点
  │      → 返回候选列表（可能 2-15 条）
  │
  ├─ 4. [可选] rerank_or_fallback(query, candidates, profile)
  │      → 如果 !ENABLED → 跳过，候选直接进入格式化
  │      → 构建 prompt（每条 excerpt ≤ 450 chars）
  │      → 调 Qwen 一次，返回 relevance 0-3 + reason
  │      → 过滤 relevance < 2
  │      → 如果 LLM 失败/非法 JSON → fallback 规则结果
  │      → 如果 LLM 返回空 + top1 distance 很强 → 保留 top1/top2
  │
  └─ 5. format_knowledge_results(selected, max_chars=profile.final_char_budget)
         → 按字符预算截断，不按条数
         → 返回给主 Agent
```

---

## 五、核心函数

### 5.1 入口

```python
# tools/knowledge_tools.py

@tool
def search_knowledge(query: str) -> str:
    """Search personal knowledge base. Returns context string."""
    return smart_search_knowledge(query)
```

### 5.2 主流程

```python
def smart_search_knowledge(query: str) -> str:
    store = get_chroma_store()
    if store.count() == 0:
        return ""

    # Step 1: 评估查询
    profile = assess_query_profile(query)

    # Step 2: 自适应探头
    raw = store.search(query, n_results=min(profile.probe_k, store.count()))
    if not raw:
        return ""

    # Step 3: 规则预筛
    candidates = rule_prefilter(raw, profile)
    if not candidates:
        return ""

    # Step 4: LLM rerank（可选）
    if ENABLE_RERANK:
        try:
            selected = llm_rerank_and_select(query, candidates, profile)
        except Exception:
            selected = candidates  # 降级：规则结果直接格式化
    else:
        selected = candidates

    if not selected:
        return ""

    # Step 5: 字符预算格式化
    return format_knowledge_results(selected, max_chars=profile.final_char_budget)
```

### 5.3 规则预筛

```python
def rule_prefilter(results: list[dict], profile: QueryProfile) -> list[dict]:
    """
    三信号联合判断：
    1. top1 是否明显优于后续（单点答案信号）
    2. 前 N 是否形成稳定相关簇（多证据信号）
    3. 是否出现大 gap（自然断点）
    """

    if not results:
        return []

    if len(results) <= 3:
        return results

    distances = [r.get("distance") for r in results if r.get("distance") is not None]
    if len(distances) < 3:
        return results[:profile.rerank_soft_limit]

    soft_limit = profile.rerank_soft_limit

    # 信号 1: top1 优势
    top1 = distances[0]
    top2 = distances[1]
    top3 = distances[2]
    top1_dominant = (top2 - top1) > 0.12 if top1 is not None else False

    # 信号 2: 前 soft_limit 条是否稳定簇
    end_idx = min(soft_limit, len(distances))
    cluster_range = distances[end_idx - 1] - distances[0]
    is_cluster = cluster_range < 0.10

    # 信号 3: gap 检测
    gaps = [distances[i + 1] - distances[i] for i in range(len(distances) - 1)]
    search_window = min(len(gaps), soft_limit)
    max_gap_idx = max(range(search_window), key=lambda i: gaps[i])
    max_gap = gaps[max_gap_idx]
    # 使用相对 gap 而非绝对值（适配不同 embedding 的量纲）
    relative_gap = max_gap / max(abs(top1), 1e-6)

    # 决策
    if top1_dominant and not is_cluster:
        # 信号 1: 前几条就够
        return results[:max(2, max_gap_idx + 1 if max_gap > 0.08 else 3)]

    if relative_gap > 0.5:
        # 信号 3: 明显断点，在断点处截断
        cut = max_gap_idx + 1
        return results[:max(cut, 2)]

    # 默认：保留 soft_limit 内所有候选
    return results[:soft_limit]
```

### 5.4 LLM 重排序

```python
def llm_rerank_and_select(query: str, candidates: list[dict], profile: QueryProfile) -> list[dict]:
    """单次 LLM 调用：relevance 打分 + 动态选择"""

    prompt = _build_rerank_prompt(query, candidates)
    response = _rerank_llm.invoke(prompt)
    content = getattr(response, "content", str(response))
    data = _parse_json_response(content)

    selected_items = data.get("selected", [])

    # 构建 id → candidate 映射
    by_label = {}
    for i, c in enumerate(candidates, 1):
        by_label[f"K{i}"] = c

    # 过滤：只保留 relevance >= 2 且 ID 合法的
    selected = []
    for item in selected_items:
        item_id = item.get("id", "")
        relevance = item.get("relevance", 0)
        if item_id in by_label and relevance >= 2:
            selected.append(by_label[item_id])

    # 查空保护：LLM 返回空但 top1 很强时，保留 top1/top2
    if not selected:
        distances = [c.get("distance") for c in candidates if c.get("distance") is not None]
        if distances and distances[0] < 0.35:
            return candidates[:2]  # top1 相关性强，保留前 2 条

    return selected
```

### 5.5 Prompt 模板

```python
def _build_rerank_prompt(query: str, candidates: list[dict]) -> str:
    blocks = []
    for i, c in enumerate(candidates, 1):
        source = c["metadata"].get("source", "")
        header = c["metadata"].get("header", "")
        # 截断 excerpt，控制 LLM 输入长度
        document = c.get("document", "")
        excerpt = document[:450]  # RERANK_EXCERPT_CHARS
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
```

### 5.6 字符预算格式化

```python
def format_knowledge_results(results: list[dict], max_chars: int) -> str:
    """按字符预算格式化，不按固定条数"""
    if not results:
        return ""

    chunks = []
    total_chars = 0

    for i, item in enumerate(results, 1):
        doc = item["document"].strip()
        source = item["metadata"].get("source", "未知来源")
        header = item["metadata"].get("header", "")

        entry = f"[K{i}]\n来源：{source}"
        if header:
            entry += f"\n标题：{header}"

        # 预算不足时：broad 保留短摘要，narrow/normal 截断
        remaining = max_chars - total_chars
        content_budget = remaining - len(entry) - 10

        if content_budget <= 0:
            break

        if len(doc) > content_budget:
            entry += f"\n内容：\n{doc[:content_budget]}..."
        else:
            entry += f"\n内容：\n{doc}"

        chunks.append(entry)
        total_chars += len(entry)

    if not chunks:
        return ""

    return "以下是你的私有知识库检索结果：\n\n" + "\n\n".join(chunks)
```

### 5.7 JSON 容错解析

```python
def _parse_json_response(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"No JSON in response: {content[:200]}")
    return json.loads(text[start:end + 1])
```

---

## 六、降级策略

| 场景 | 行为 |
|------|------|
| `RERANK_ENABLED=false` | 跳过 LLM，规则预筛结果直接进入字符预算格式化 |
| LLM 返回非 JSON | 降级为规则预筛结果 |
| LLM 超时/异常 | 降级为规则预筛结果 |
| LLM 返回空 `selected` 数组 | 查空保护：如果 top1 distance < 0.35，保留 top1/top2；否则返回 `""` |
| `selected` 中含非法 ID | 过滤非法 ID，剩余为空则降级为规则结果 |
| ChromaDB 返回 < 3 条 | 直接返回，不走 LLM |
| 知识库为空 | 返回 `""` |

---

## 七、三个典型场景

| 场景 | profile | probe_k | LLM 行为 | 返回 |
|------|---------|---------|----------|------|
| "我的手机号是多少" | narrow | 10 | 选 1 条或 0 条 | 1 条（~500 chars）或空 |
| "search_knowledge 当前流程" | normal | 20 | 选 3-6 条互补 | 3-5 条（~2500 chars） |
| "对比所有 AI 架构笔记" | broad | 30 | 可选 8-12 条互补 | 按 5000 chars 预算填充 |
| "某个冷门概念"（KB 中只有 2 条） | narrow/normal | 10/20 | 选 2 条或 0 条 | 2 条或空 |

---

## 八、工具缓存适配

```python
# agent/tools.py 中缓存 key 版本升级
CACHE_PREFIX = "smart_v2"

# ReflexionState 中：
state.cache_tool_result(f"{CACHE_PREFIX}:kb", query, result)
state.get_cached_tool_result(f"{CACHE_PREFIX}:kb", query)
```

缓存仅在单次请求内有效，v1→v2 版本前缀变更后旧缓存自然失效。

---

## 九、文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `tools/knowledge_tools.py` | **重写** | 新增 `assess_query_profile` / `rule_prefilter` / `llm_rerank_and_select` / `format_knowledge_results` |
| `agent/tools.py` | **微调** | cache prefix → `smart_v2` |
| `agent/reflexion.py` | **不改** | ReflexionState 缓存机制不变 |
| `config/settings.py` | **可能不改** | 配置从环境变量读取，`os.getenv()` 足够；如需 pydantic 字段可后续加 |
| `tests/test_knowledge_tools.py` | **新建** | 检索优化单元测试（见测试策略） |
| `docs/SMART_SEARCH_DESIGN.md` | **本文件** | 方案 A++ 设计文档 |

---

## 十、测试策略

| 类型 | 用例 | 数量 |
|------|------|------|
| 单元 | `assess_query_profile` narrow/normal/broad/边界 | 8 |
| 单元 | `rule_prefilter` top1 优势/稳定簇/大 gap/不足 3 条 | 6 |
| 单元 | `llm_rerank_and_select` — mock LLM 返回各种 relevance 组合 | 5 |
| 单元 | `llm_rerank_and_select` — 查空保护：LLM 空但 top1 < 0.35 | 2 |
| 单元 | `_parse_json_response` 纯 JSON/markdown 包裹/无 JSON/嵌套括号 | 5 |
| 单元 | `format_knowledge_results` 字符预算截断/空/不足预算 | 4 |
| 单元 | `smart_search_knowledge` mock ChromaDB + mock LLM（3 个 profile） | 5 |
| 集成 | 完整流程（ChromaDB 有数据 + rerank 开/关，3 个 profile） | 6 |
| 降级 | LLM 异常/非 JSON/非法 ID/ChromaDB 空/查空 | 5 |
| 场景 | 简单事实/普通解释/综合查询/稀疏关联/无关查询 | 5 |
| **合计** | | **51** |

### 注意事项

- distance 阈值（0.12 / 0.08 / 0.35 / 0.5）需要用实际知识库跑查询样例校准，测试中先用 mock distance 覆盖逻辑分支
- 不要要求测试精确验证"返回了几条"——预期应使用范围断言（如 `0 <= len(result) <= 4`）而非精确断言
- LLM 相关测试全部 mock，不调真实 DeepSeek/Qwen
- 兼容现有 258 测试，不破坏任何已有用例

---

## 十一、实施步骤

```
Step 1: 在 tools/knowledge_tools.py 中实现所有新增函数
Step 2: search_knowledge 委托到 smart_search_knowledge
Step 3: agent/tools.py 缓存前缀改为 smart_v2
Step 4: 写 51 个测试（mock LLM / mock ChromaDB）
Step 5: 本地起服务，用真实知识库跑查询样例，校准 distance 阈值
Step 6: 对比优化前后检索质量
Step 7: 同步文档（README / TECH_DEBT / CLAUDE.md）
```

---

## 十二、风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| distance 阈值不适合当前 embedding | 用实际查询样例校准，使用相对 gap 而非绝对值 |
| Qwen2.5:7b 输出不稳定（多选/少选/非法 JSON） | JSON 容错解析 + relevance ≥2 过滤 + 查空保护 + 降级路径 |
| broad 查询返回过多撑爆 Agent 上下文 | `final_char_budget` 最终裁剪，最大 5000 chars |
| 缓存 key 策略变更导致调试混淆 | 版本前缀 `smart_v2`，与 v1 隔离 |
| broad 查询 LLM 选出的条目内容重复 | prompt 强调"优先选择互补信息，不要只选相似片段" |

---

> **设计日期：** 2026-07-01
> **方案代号：** A++（自适应召回、动态证据选择与上下文预算控制）
> **上一版本：** A+（已废弃，见 `110d346`）
