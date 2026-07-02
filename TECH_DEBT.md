# 技术债务文档

> 记录当前版本已知的设计缺陷和待改进项，供后续版本逐步修复。
>
> **v0.5 更新：** 被动记忆提取、统一 LLM 配置、知识库管理、冲突检测已完成。当前主要债务：ChromaDB 多进程支持、embedding 性能。

---

## v0.5 已修复

| 问题 | 修复 |
|---|---|
| LLM 不按格式返回 JSON | 重写 prompt + `_normalize_candidates()` 格式适配器 |
| 编辑文本块消失 | ChromaDB `col.update()` 替代 delete+add |
| 被动提取不产生候选 | 格式适配 + prompt 简化 |
| 搜索返回无关结果 | 删除空结果兜底逻辑 |
| get_chroma_store() 多实例 | `@lru_cache` 单例 |
| 聊天不加载历史 | ChatService 注入历史消息 |
| os.path 导入 | 统一使用 pathlib.Path |
| update_chunk 不安全 | 改用原生 update 方法 + 线程锁 |

## v0.5 遗留

- ChromaDB PersistentClient 不支持多 worker → 单 worker 部署
- embedding 调用 Ollama 较慢（~2.4s/次）→ 可考虑异步或批量优化
- 前端单文件 ~1600 行 → 可拆分模块

---

## 已完成的修复（v0.2）

### P0：AgentState 三方定义不一致
**问题描述：**
`state.py`、`graph.py`、`chat_service.py` 三个文件对 AgentState 的字段定义和使用完全不匹配。

**修复方案：**
- 统一使用 GraphState 定义
- 添加 remaining_steps 字段
- 保持 AgentState 别名向后兼容

**状态：** 已完成

---

### P0：双聊天执行管线导致行为不一致
**问题描述：**
`/chat` 和 `/chat/stream` 是两条独立的业务管线。

**修复方案：**
- 引入 ChatService 统一消息管线
- `/chat` 和 `/chat/stream` 都调 `ChatService.stream_events()`
- `/chat` 收集最终结果后返回 JSON
- `/chat/stream` 逐条推送事件

**状态：** 已完成

---

### P0：detect_intent 已被工具调用替代
**问题描述：**
当前 `detect_intent` 节点让 LLM 输出一个模糊的 `intent` 字符串，然后根据字符串路由。

**修复方案：**
- 删除独立的 `detect_intent` 节点
- Qwen 直接绑定 `bind_tools()`，输出结构化 tool_calls
- 确定性 UI 操作（点击按钮）不走 LLM，直接调 API

**状态：** 已完成

---

### P0：Ollama 不可用时无降级处理
**问题描述：**
如果 Ollama 没有在运行，整个 Agent 直接崩溃。

**修复方案：**
- 在每个 node 外层加 try/except
- 或加一个全局的错误处理 node
- 或使用 LangGraph 的 fallback 机制

**状态：** 已完成

---

### P0：不支持删除和修改记忆
**问题描述：**
没有提供删除或修改已有记忆的途径。

**修复方案：**
- graph 中增加 `forget` / `update` 意图
- 前端记忆面板增加删除按钮

**状态：** 已完成

---

### P0：被动记忆提取——用户必须主动说"记住"
**问题描述：**
目前只有用户明确说"记住..."时才保存记忆。

**设计方案：**
不做逐句解析。改为**定期批量分析**：
- 时机：每周复盘时（或每天空闲时）
- 输入：最近 N 条对话消息
- 输出：LLM 分析对话，提取潜在记忆
- 保存方式：置信度 0.6，标记为"需确认"

**状态：** 计划中（v0.3）

---

### P0：Agent 问答可靠性差
**问题描述：**
qwen2.5:7b 指令跟随能力有限，JSON 输出不稳定。

**修复方案：**
- 使用 bind_tools() 替代 JSON 解析
- 工具调用更稳定
- 减少对 LLM 输出格式的依赖

**状态：** 已完成

---

## 待修复的问题

### P1：模型名硬编码
**问题描述：**
`agent/graph.py` 中 `"qwen2.5:7b"` 硬编码。

**修复方案：**
改为 `settings.ollama_chat_model`。

**状态：** 已完成

---

### P1：JSON 解析不稳定
**问题描述：**
qwen2.5:7b 的 JSON 输出经常解析失败。

**修复方案：**
使用 bind_tools() 替代 JSON 解析。

**状态：** 已完成

---

### P1：会话管理
**问题描述：**
没有会话列表、切换、删除功能。

**修复方案：**
- 前端侧边栏 + 新建/切换/删除/重命名
- 后端 `/conversations` CRUD + `/rename` API
- 消息自动保存

**状态：** 已完成（v0.3）

---

### P2：流式协议标准化
**问题描述：**
SSE 事件格式没有文档化。

**修复方案：**
- 定义事件类型和 payload 结构
- 前端按事件类型分发处理

**状态：** 已完成

---

### P2：对话管理
**问题描述：**
无法查看历史对话。

**修复方案：**
- SQLite 已有 conversations 和 messages 表
- 前端侧边栏 + 历史消息加载
- 后端完整 CRUD API

**状态：** 已完成（v0.3）

---

### P2：Agent 检索
**问题描述：**
知识库检索结果不够精准。

**修复方案：**
- 智能检索 A++（LLM 查询分类 → 自适应探头 → gap 预筛 → relevance 重排序 → 字符预算格式化）
- 53 单元测试 + 7 集成测试
- 距离阈值已校准（nomic-embed-text 768维 L2）

**状态：** 已完成（v0.3 A++）

---

### P2：安全
**问题描述：**
敏感信息可能泄露。

**修复方案：**
- 输入验证
- 输出过滤
- 权限控制

**状态：** 已完成

---

### P3：Reflexion 循环（带缓存 + 结构化反馈 + 智能终止）
**问题描述：**
Agent 不会从失败中学习，同样的问题第二次还是同样错误。

**设计方案：**

#### 核心优化

1. **临时缓存列表（带归一化）**
   - 循环外维护缓存字典
   - Agent 查数据时先查缓存
   - 缓存没有再查数据库
   - **缓存 key 标准化归一化**：`"Redis 配置"` 和 `"redis 配置"` 命中同一缓存
   - **缓存作用域**：单次请求内有效，跨请求不共享

2. **结构化反馈**
   - issues 和 suggestions 结构化，而不是纯字符串
   - 每条 issue 对应一条 suggestion
   - Agent 在下一轮可以逐条针对性修正
   - 避免面对一段模糊的批评不知所措

3. **智能终止**
   - 连续两次分数没有提升 → 提前终止
   - 避免"改了三遍反而越来越差"的情况
   - 节省 token 和时间

4. **最低分数线**
   - score < 4 返回 None
   - 前端显示"抱歉，我暂时无法回答这个问题"
   - 比返回一个低质量回答更好

#### 数据结构设计

```python
@dataclass
class ReviewResult:
    """审核结果"""
    score: int              # 1-10
    passed: bool            # score >= 7 算通过
    issues: List[str]       # ["格式不符合 Markdown 规范", "第3条引用不存在"]
    suggestions: List[str]  # ["使用无序列表", "验证 K3 来源是否存在"]

@dataclass
class ReflexionAttempt:
    """一次 Reflexion 循环的尝试"""
    attempt: int  # 第几次尝试
    answer: str  # Agent 的回答
    review: ReviewResult  # 审核结果（结构化）
    cached_data: dict  # 缓存的数据

class ReflexionState:
    """Reflexion 循环状态"""
    def __init__(self):
        self.attempts: List[ReflexionAttempt] = []  # 所有尝试
        self.cache: dict = {}  # 临时缓存（单次请求内有效）
        self.question: str = ""  # 原始问题
    
    def _normalize_key(self, query: str) -> str:
        """缓存 key 标准化归一化"""
        return query.strip().lower()
    
    def cache_data(self, key: str, value: any):
        """缓存数据（带归一化）"""
        normalized_key = self._normalize_key(key)
        self.cache[normalized_key] = value
    
    def get_cached_data(self, key: str) -> Optional[any]:
        """获取缓存的数据（带归一化）"""
        normalized_key = self._normalize_key(key)
        return self.cache.get(normalized_key)
    
    def get_best_attempt(self, min_score: int = 4) -> Optional[ReflexionAttempt]:
        """获取得分最高的尝试（带最低分数线）"""
        valid = [a for a in self.attempts if a.review.score >= min_score]
        return max(valid, key=lambda x: x.review.score) if valid else None
    
    def get_passed_attempt(self) -> Optional[ReflexionAttempt]:
        """获取通过的尝试"""
        for attempt in self.attempts:
            if attempt.review.passed:
                return attempt
        return None
    
    def should_terminate_early(self) -> bool:
        """判断是否应该提前终止（连续两次分数没有提升）"""
        if len(self.attempts) < 2:
            return False
        return self.attempts[-1].review.score <= self.attempts[-2].review.score
```

#### 循环流程

```
用户输入
    ↓
┌─────────────────────────────────────┐
│ 初始化 ReflexionState               │
│   - attempts: []  # 所有尝试        │
│   - cache: {}  # 临时缓存           │
│   - question: ""  # 原始问题        │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 循环开始（最大 3 次）                │
│   ↓                                 │
│   Agent 生成答案（使用缓存）          │
│   ↓                                 │
│   审核员检查（结构化反馈）            │
│   ↓                                 │
│   记录回答和审核结果                  │
│   ↓                                 │
│   判断是否通过                       │
│   ├─ 通过 → 返回通过的回答           │
│   └─ 不通过 → 检查提前终止条件       │
│       ├─ 连续两次分数没提升 → 终止   │
│       └─ 继续循环                    │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 循环结束                             │
│   ↓                                 │
│   获取得分最高的回答（最低分数线 4）  │
│   ├─ 有 → 返回得分最高的回答         │
│   └─ 无 → 返回 None                  │
│       └─ 前端显示"暂时无法回答"       │
└─────────────────────────────────────┘
```

**适用场景：** 代码生成、JSON 输出、知识库引用检查
**不适用：** 主观创意类、本地小模型自我反思

**状态：** 已完成（v0.3，详见下方"v0.3 已完成的修复"）

---

### P3：多 Agent 审核循环
**问题描述：**
Agent 不会从失败中学习。

**设计方案：**
```
1. Agent 生成回答
2. 审核员指出不足
3. Agent 根据反馈修改回答
4. 循环直到通过或最大次数
```

**适用场景：** 代码生成、JSON 输出、知识库引用检查
**不适用：** 主观创意类、本地小模型自我反思

**状态：** 计划中（v0.4）

---

## v0.3 已完成的修复

### Reflexion 循环实现
- ReflexionState + 工具层数据缓存（contextvars 传递 state）
- DeepSeek 审核员检查
- 缓存下沉到工具层（缓存原始数据，不缓存 LLM 答案）
- 接口精简（get_best_attempt 替代 get_passed_attempt）
- 反馈与原始问题分离
- JSON 解析三层容错（直接解析 / ```json``` 代码块 / regex 提取）
- DeepSeek API 异常保护（401/429/5xx/超时/网络异常）
- 降级兜底（Reflexion 失败自动走 ReAct）
- 100 个新测试（ReflexionState、审核模块、DeepSeek 客户端、工具缓存、集成、安全）

### chromadb 兼容性修复
- 同时捕获 NotFoundError + InvalidCollectionException

### settings.py 重构
- 删除重复字段
- API key 从源码移除，仅从 .env 读取
- 删除 class Config，统一使用 model_config

---

## 修复路线图

| 版本 | 修复项 |
|------|--------|
| v0.2（已完成） | P0：AgentState 统一、双管线统一、工具调用替代 intent、Ollama 降级、删除记忆、问答可靠性 |
| v0.2（已完成） | P1：模型名配置化、JSON 解析、流式协议标准化 |
| v0.3（已完成） | Reflexion 循环、工具层缓存、DeepSeek 审核、chromadb 兼容、废弃代码清理 |
| v0.3（已完成） | P2：智能检索 A++（规则分类 + 自适应探头 + gap 预筛 + relevance 重排序 + 字符预算 + LLM 合并） |
| v0.3（已完成） | P1/P2：对话管理（侧边栏 + 新建/切换/重命名/删除 + 消息保存 + 打字机效果） |
| v0.3（计划中） | 被动记忆提取 |
| v0.4（计划中） | P3：多 Agent 审核循环、独立 search agent |

---

## v0.2 架构变更（已实施）

### 核心变化：任务分解 + ReAct 循环替代 DeepSeek 子问题规划

原方案的 Phase 2 规划图：

```
复杂问题 → DeepSeek 拆子问题 → 逐个交给 Qwen 执行 → 合成答案
```

这个方案有三个问题：
1. **Token 消耗高** — 每个子问题独立调用 LLM，上下文不能复用
2. **数据库调用多** — 子问题各自查知识库，同类查询无法合并
3. **DeepSeek 依赖** — 每次复杂问题都要走 API，成本和延迟增加

### 优化后的方案

```
用户输入
    ↓
Qwen + bind_tools()
    ├─ 没有 tool_calls → 直接 chat 回答
    └─ 有 tool_calls → 执行工具 → 结果传回 LLM
         ↓
         △(如果还有未完成任务)
    ReAct 循环节点:
        ┌─────────────────────────────────────────────────────────────────────┐
        │ Qwen 决策 → 调用工具 → 观察结果                                     │
        │           → 自评完成度                                              │
        │           → 继续 / 任务完成 / 最大轮次                               │
        └─────────────────────────────────────────────────────────────────────┘
         ↓
         △(全部完成)
    合成最终回答
```

---

## v0.3 架构变更（已完成）

### 核心变化：Reflexion 循环（带缓存 + 结构化反馈 + 智能终止）+ 智能检索 A++

**Claude 评审意见：**

> 你的设计思路很扎实，三个优化点都切中了当前 ReAct 循环的实际痛点。

**评审维度：**

| 维度 | 评分 | 说明 |
|------|------|------|
| 问题定位 | ★★★★★ | 准确抓住了 ReAct 的三个弱点 |
| 数据结构 | ★★★★☆ | ReflexionAttempt 设计清晰，ReviewResult 建议结构化 |
| 边界处理 | ★★★☆☆ | 需要补全失败、连续退化、低分兜底等边界 |
| 可实现性 | ★★★★★ | 完全可以基于当前 agent/tools.py + agent/state.py 扩展 |

**吸收的优化建议：**

1. **缓存 key 标准化归一化**
   - `"Redis 配置"` 和 `"redis 配置"` 应该命中同一个缓存
   - 使用 `query.strip().lower()` 归一化

2. **缓存作用域明确**
   - 缓存在单次请求内有效，跨请求不共享
   - 避免以后有人误解为全局缓存

3. **结构化反馈**
   - issues 和 suggestions 结构化，而不是纯字符串
   - 每条 issue 对应一条 suggestion
   - Agent 在下一轮可以逐条针对性修正

4. **最低分数线**
   - score < 4 返回 None
   - 前端显示"抱歉，我暂时无法回答这个问题"
   - 比返回一个低质量回答更好

5. **智能终止**
   - 连续两次分数没有提升 → 提前终止
   - 避免"改了三遍反而越来越差"的情况

**与当前代码的衔接点：**

- ReflexionState 可以直接扩展当前的 GraphState（在 agent/state.py 里加字段）
- 带缓存的 search_knowledge_with_cache 包装现有的 tools/knowledge_tools.py
- reflexion_loop 替代当前的 create_react_agent，或者作为它的外层包装

**结论：** 这个设计可以在不破坏现有 v0.2 架构的前提下实现，说明 v0.2 的模块划分是合理的。

---

**决策日期：** 2026-06-30
**决策人：** Tech Lead + 用户 + Claude 共同审核
**诱因：** 用户提出优化方案，Claude 提供专业评审意见

---

## v0.3 A++ 智能检索（已实施）

**实施方案：** [docs/SMART_SEARCH_DESIGN.md](docs/SMART_SEARCH_DESIGN.md)

**核心管线：**
```
LLM 查询分类 (narrow/normal/broad)
  → 自适应 ChromaDB 探头 (10/20/30)
  → distance gap 规则预筛
  → LLM relevance 打分 (0-3, 只保留 >=2)
  → 字符预算格式化 (1800/3000/5000 chars)
```

**关键设计决策：**
- 查询复杂度用 LLM 分类（非规则），为后续多 agent 框架做准备
- 不设固定返回条数上限，改为字符预算约束
- 允许返回空结果
- 查空保护：LLM 判断空时保留 top 2 兜底
- 距离阈值已校准：nomic-embed-text 768 维 L2 量纲 ~1.0-1.15

**文件变更：**
| 文件 | 变更 |
|------|------|
| `tools/knowledge_tools.py` | 重写，新增 8 个函数 + QueryProfile |
| `agent/tools.py` | 缓存前缀 `kb` → `kb_v2` |
| `tests/test_knowledge_tools.py` | 新建，60 测试（53 单元 + 7 集成） |
| `pytest.ini` | 新建，注册 integration marker |

**实施日期：** 2026-07-01
