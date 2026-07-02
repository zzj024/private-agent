# Bug 记录

## BUG-001：被动记忆提取不生成审核候选

**发现时间**：2026-07-02
**严重程度**：中
**状态**：待修复

### 现象

用户在聊天中明确表达了个人偏好（喜欢 Python、常用 VS Code、不喜欢啰嗦回答），等待超过 2 分钟后：

1. 「📚 记忆库」中出现了一条 `favorite_test_color: 青绿色`，但来源标注为「手动记录」（explicit），说明是 Agent 聊天时主动调了 `save_memory` 工具写入的，**不是被动提取管线产生的**。
2. 「✅ 审核」列表始终为空，**没有出现任何 passive 候选**。
3. 用户多次发送偏好信息后仍然没有候选。

### 预期行为

被动提取管线应该：
1. 聊天消息落库
2. 2 分钟后 `schedule_passive_memory_extraction()` 触发
3. LLM（Qwen）分析最近 12 条消息，提取候选记忆
4. v0.5 自动分级：高可信 → auto_accepted，中信 → pending（审核列表），低信 → auto_rejected
5. 结果应在审核列表或记忆库中可见

### 可能原因

1. `passive_memory_enabled` 配置可能未生效
2. `schedule_passive_memory_extraction` 的 timer 可能没有正确触发
3. LLM 提取返回的 JSON 解析失败（`_extract_json` 容错不够）
4. v0.5 自动分级阈值设置问题——高可信的直接 auto_accepted（但用户说记忆库里也没有新记忆），低可信的 auto_rejected 不会出现在审核列表
5. threading.Timer 在 uvicorn reload 模式下可能存在问题

### 临时验证方法

```bash
# 检查被动提取是否被禁用
python -c "from config.settings import settings; print(settings.passive_memory_enabled)"

# 手动触发提取测试
python -c "
from memory.passive_extractor import extract_passive_memories
from memory.sqlite_store import get_store
store = get_store()
# 找一个有消息的会话
convs = store.get_recent_conversations(5)
for c in convs:
    msgs = store.get_conversation_messages(c['id'])
    print(f'Conv {c[\"id\"]}: {len(msgs)} messages')
    if len(msgs) >= 2:
        print(f'  Triggering extraction for conv {c[\"id\"]}...')
        extract_passive_memories(c['id'])
        break
"
```

### 影响范围

- v0.5 被动记忆提取核心功能不可用
- 用户无法通过聊天自动积累记忆
- 记忆审核页面始终为空（除非手动调用 save_memory）

---

## BUG-003：导入完成 Toast 重复弹出（已修复）

**状态**：✅ 已修复 (2026-07-02)

轮询每 0.8s 检测到 status==='done' 就弹一次 toast，一个文件完成会弹多次。
修复：给每个文件加 `notified` 标记，只在首次检测到完成/失败时弹一次。

---

## BUG-002：审核候选编辑后消失（已修复）

**状态**：✅ 已修复 (2026-07-02)

根因：`update_chunk()` 使用 delete+add 模式，add 失败导致数据丢失。
修复：改用 ChromaDB 原生 `col.update()` 方法；`get_chroma_store()` 改为单例。

---

## BUG-004：编辑文本块保存太慢

**状态**：待优化

每次编辑保存需要约 2.4 秒，原因是 `col.update()` 触发 Ollama 重新 embedding。

---

## BUG-005：知识库搜索无结果词仍返回结果

**状态**：待修复

输入 `asdfghjkl不存在的词999` 搜索，仍然返回了结果。根因在 `tools/knowledge_tools.py` 的 `llm_rerank_and_select()` 中有查空保护逻辑：

```python
if not selected and len(candidates) >= 1:
    return candidates[:2]  # 兜底返回前 2 条
```

LLM 判断全部不相关返回空数组时，这段代码强制返回前 2 条作为"安全兜底"，导致无关词也能搜到东西。应改为：LLM 明确说都不相关时，尊重 LLM 判断，返回空。

---

## BUG-006：知识库搜索结果太少，无法浏览全部相关块

**状态**：待修复

搜索 `redis` 只返回 1 条结果，但实际上知识库中有大量相关内容。问题：
1. 搜索结果没有分页，只能看到 LLM 筛选后的几条
2. 搜索结果不能编辑/删除/查看完整内容
3. 应该像已导入文件那样，支持分页浏览所有相关文本块，并允许编辑删除

期望：搜索结果分页展示，每页 15 条，支持编辑和删除。
