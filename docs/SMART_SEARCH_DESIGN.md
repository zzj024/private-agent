# 智能检索实施方案（v0.3 P2）

> 版本：v1.0  
> 日期：2026-07-01  
> 状态：待实施

---

## 一、目标

将 `search_knowledge` 从固定 Top-5 升级为智能检索，不改签名，不引入独立 agent。

```
当前: ChromaDB Top-5 → 格式化 → 返回
目标: ChromaDB Top-20 → 规则剪枝 → LLM 重排序 → 动态选择 → 返回
```

---

## 二、设计决策

| 决策 | 结论 | 原因 |
|------|------|------|
| 是否做成独立 search agent | **不做** | 当前 96 chunks 规模不需要，多 agent 框架留给 v0.4 |
| LLM 调用次数 | **1 次** | 只在重排序环节调 LLM，数量决策合并到同一个 prompt |
| 规则 vs LLM 分工 | **规则控边界 + LLM 判语义** | 资源控制（最大候选数、超时、降级）归规则，相关性判断归 LLM |
| 签名 | **不变** | `search_knowledge(query: str) -> str`，调用方无感知 |
| 可关闭 | **是** | `KNOWLEDGE_ENABLE_RERANK=false` 即可回退 |
| 与工具缓存兼容 | **是** | cache key 加 `smart_v1` 前缀 |

---

## 三、数据流

```
search_knowledge(query)
  │
  ├─ 1. ChromaDB.search(query, n_results=20)
  │      → 20 条候选，含 distance
  │
  ├─ 2. normalize_candidates()
  │      → 统一内部格式 [{rank, id, document, metadata, distance}, ...]
  │
  ├─ 3. select_rerank_candidates(candidates)
  │      → 根据距离分布规则，选出 5~8 条给 LLM
  │      → 规则: gap_1_to_5 大 → 5条; top5 平缓 → 8条; 否则 6条
  │
  ├─ 4. [可选] _llm_rerank_and_select(query, candidates)
  │      → 如果 KNOWLEDGE_ENABLE_RERANK=false，跳过此步，直接取前 MAX_FINAL_RESULTS 条
  │      → 构建 prompt，调 Qwen 一次
  │      → 解析 JSON，提取 selected_ids
  │      → 返回按相关性排序的最终候选
  │
  └─ 5. format_context(selected)
         → 格式化为 [K1]...[Kn] 编号块
         → 超过 MAX_CONTEXT_CHARS 截断
         → 返回给主 Agent
```

---

## 四、配置项

`.env` 新增：

```env
# 智能检索
KNOWLEDGE_PROBE_N=20
KNOWLEDGE_MAX_RERANK_CANDIDATES=8
KNOWLEDGE_MIN_FINAL_RESULTS=1
KNOWLEDGE_MAX_FINAL_RESULTS=5
KNOWLEDGE_MAX_CONTEXT_CHARS=3000
KNOWLEDGE_ENABLE_RERANK=true
```

---

## 五、文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `tools/knowledge_tools.py` | **重写** | 新增 smart_search_knowledge + 辅助函数 |
| `agent/tools.py` | **不改** | `search_knowledge` 工具签名不变，内部委托给 `tools/knowledge_tools.search_knowledge` |
| `config/settings.py` | **不改** | 配置从环境变量读取，不需要 pydantic 字段 |
| `tests/test_knowledge_tools.py` | **新建** | 检索优化单元测试 |
| `docs/SMART_SEARCH_DESIGN.md` | **本文件** | 实施方案文档 |

---

## 六、核心函数

### 6.1 入口函数

```python
# tools/knowledge_tools.py

@tool
def search_knowledge(query: str) -> str:
    """Search personal knowledge base. Use when you need to query user notes, documents, or project information."""
    return smart_search_knowledge(query)
```

### 6.2 主流程

```python
def smart_search_knowledge(query: str) -> str:
    store = get_chroma_store()
    if store.count() == 0:
        return ""

    # Step 1: Probe
    candidates = store.search(query, n_results=PROBE_N)
    if not candidates:
        return ""
    candidates = _normalize_candidates(candidates)

    # Step 2: Rule-based pruning
    rerank_pool = _select_rerank_candidates(candidates)

    # Step 3: LLM rerank (optional)
    if ENABLE_RERANK:
        try:
            selected = _llm_rerank_and_select(query, rerank_pool)
        except Exception:
            selected = rerank_pool[:MAX_FINAL_RESULTS]
    else:
        selected = rerank_pool[:MAX_FINAL_RESULTS]

    # Step 4: Format
    return _format_context(selected)
```

### 6.3 候选归一化

```python
def _normalize_candidates(results: list[dict]) -> list[dict]:
    output = []
    for idx, item in enumerate(results, start=1):
        doc = item.get("document", "").strip()
        if not doc:
            continue
        output.append({
            "rank": idx,
            "id": item.get("id"),
            "document": doc,
            "metadata": item.get("metadata", {}),
            "distance": item.get("distance"),
        })
    return output
```

### 6.4 规则剪枝

```python
def _select_rerank_candidates(candidates: list[dict]) -> list[dict]:
    """基于距离分布选择给 LLM 重排序的候选数量"""

    if len(candidates) <= MAX_RERANK_CANDIDATES:
        return candidates

    distances = [c["distance"] for c in candidates if c.get("distance") is not None]

    if len(distances) < 5:
        return candidates[:MAX_RERANK_CANDIDATES]

    top1 = distances[0]
    top3_mean = sum(distances[:3]) / 3
    top5_mean = sum(distances[:5]) / 5
    gap_1_to_5 = distances[4] - distances[0]

    # Top 集中 → 问题明确，少量候选够
    if gap_1_to_5 > 0.15:
        k = 5
    # Top5 平缓 → 可能需要更多候选让 LLM 判断
    elif abs(top5_mean - top1) <= 0.08:
        k = MAX_RERANK_CANDIDATES
    else:
        k = 6

    k = max(3, min(k, MAX_RERANK_CANDIDATES, len(candidates)))
    return candidates[:k]
```

### 6.5 LLM 重排序

```python
def _llm_rerank_and_select(query: str, candidates: list[dict]) -> list[dict]:
    prompt = _build_rerank_prompt(query, candidates)
    response = _rerank_llm.invoke(prompt)
    content = getattr(response, "content", str(response))
    data = _parse_json_response(content)
    selected_ids = data.get("selected_ids", [])

    by_label = {f"K{i+1}": c for i, c in enumerate(candidates)}
    selected = [by_label[l] for l in selected_ids if l in by_label]

    if not selected:
        return candidates[:MIN_FINAL_RESULTS]

    return selected[:MAX_FINAL_RESULTS]
```

### 6.6 Prompt 模板

```python
def _build_rerank_prompt(query: str, candidates: list[dict]) -> str:
    blocks = []
    for i, c in enumerate(candidates, 1):
        source = c["metadata"].get("source", "")
        header = c["metadata"].get("header", "")
        blocks.append(
            f"[K{i}] distance={c['distance']:.4f} source={source}\n"
            f"header={header}\ncontent: {c['document']}"
        )

    return f"""Rank these knowledge chunks by relevance to the query.
Return only the ones that actually help answer the question.
Select {MIN_FINAL_RESULTS}-{MAX_FINAL_RESULTS} chunks.

Query: {query}

Candidates:
{chr(10).join(blocks)}

Return JSON only:
{{"selected_ids": ["K1","K3"], "reason": "..."}}
"""
```

### 6.7 JSON 容错解析

```python
def _parse_json_response(content: str) -> dict:
    text = content.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    # Extract outermost { }
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"No JSON in response: {content[:200]}")
    return json.loads(text[start:end + 1])
```

### 6.8 格式化输出

```python
def _format_context(selected: list[dict]) -> str:
    if not selected:
        return ""

    chunks, total = [], 0
    for i, item in enumerate(selected, 1):
        doc = item["document"].strip()
        source = item["metadata"].get("source", "未知来源")
        header = item["metadata"].get("header", "")

        entry = f"[K{i}]\n来源：{source}"
        if header:
            entry += f"\n标题：{header}"
        entry += f"\n内容：\n{doc}"

        if total + len(entry) > MAX_CONTEXT_CHARS:
            break
        chunks.append(entry)
        total += len(entry)

    return "以下是你的私有知识库检索结果：\n\n" + "\n\n".join(chunks)
```

---

## 七、降级策略

| 场景 | 行为 |
|------|------|
| `ENABLE_RERANK=false` | 跳过 LLM，直接取规则剪枝后的 Top-N |
| LLM 返回非 JSON | 降级为规则 Top-N |
| LLM 超时/异常 | 降级为规则 Top-N |
| `selected_ids` 为空 | 返回规则 Top-N（至少 MIN_FINAL_RESULTS 条） |
| ChromaDB 返回 < 3 条 | 直接返回，不走 LLM |
| 知识库为空 | 返回 `""` |

---

## 八、工具缓存适配

```python
# agent/tools.py 中 search_knowledge 调 knowledge_tools 时：
# 缓存 key 加版本前缀，prompt 变更后自然失效

# agent/reflexion.py ReflexionState 中：
CACHE_PREFIX = "smart_v1"
state.cache_tool_result(f"{CACHE_PREFIX}:kb", query, result)
state.get_cached_tool_result(f"{CACHE_PREFIX}:kb", query)
```

---

## 九、测试策略

| 类型 | 用例 | 数量 |
|------|------|------|
| 单元 | `_normalize_candidates` 空输入/正常输入/无 distance 字段 | 5 |
| 单元 | `_select_rerank_candidates` 集中分布/平缓分布/不足 5 条/恰好 MAX | 6 |
| 单元 | `_parse_json_response` 纯 JSON/markdown 包裹/无 JSON/嵌套括号 | 5 |
| 单元 | `_format_context` 空/1 条/超 MAX_CONTEXT_CHARS 截断 | 4 |
| 单元 | `smart_search_knowledge` mock ChromaDB 返回/mock LLM 返回 | 5 |
| 集成 | 完整流程（ChromDB 有数据 + LLM rerank 开/关） | 3 |
| 降级 | LLM 异常/非 JSON/ChromDB 空 | 3 |
| **合计** | | **31** |

---

## 十、实施步骤

```
Step 1: 在 tools/knowledge_tools.py 中实现所有辅助函数
Step 2: 改 search_knowledge 委托到 smart_search_knowledge
Step 3: 在 agent/reflexion.py 的缓存前缀改为 smart_v1
Step 4: 写 31 个测试
Step 5: 本地起服务，对比优化前后检索质量
Step 6: 同步文档（README TECH_DEBT 等）
```
