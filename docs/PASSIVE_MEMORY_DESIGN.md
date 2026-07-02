# 被动记忆提取 — Phase 1 实施文档

> 版本：v1.0
> 日期：2026-07-01
> 状态：待实施
> 策略：所有候选进 pending，不做自动写入

---

## 一、目标

让系统从日常对话中**自动**提取用户信息，作为"候选记忆"提交给用户审核。Phase 1 最安全：不自动写入任何记忆。

```
对话结束 → assistant 消息落库 → 后台延迟 120s → Qwen 提取候选 → pending → 用户审核
```

## 二、核心原则

| 原则 | 说明 |
|------|------|
| 不阻塞主路径 | 提取在 daemon 线程中跑，/chat/stream 不受影响 |
| 失败静默丢弃 | 提取异常不报错、不写候选 |
| 全部待确认 | Phase 1 不进 memories，只进 memory_candidates |
| 向后兼容 | `save_memory("k","v","cat")` 行为不变 |
| 不破坏测试 | 318 个已有测试全部保持通过 |

## 三、数据模型

### 3.1 新表：memory_candidates

```sql
CREATE TABLE IF NOT EXISTS memory_candidates (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    key                     TEXT    NOT NULL,
    value                   TEXT    NOT NULL,
    category                TEXT    DEFAULT '',
    confidence              REAL    DEFAULT 0.5,
    importance              REAL    DEFAULT 0.5,
    sensitivity             TEXT    DEFAULT 'low',
    action                  TEXT    DEFAULT 'store',
    evidence                TEXT    DEFAULT '',
    reason                  TEXT    DEFAULT '',
    source_conversation_id  INTEGER,
    source_message_ids      TEXT    DEFAULT '[]',
    status                  TEXT    DEFAULT 'pending',
    created_at              TEXT    DEFAULT (datetime('now','localtime')),
    reviewed_at             TEXT
);
```

status 取值：`pending` | `accepted` | `rejected` | `auto_accepted`（Phase 2 用）

### 3.2 旧表加列：memories

用 ALTER TABLE 逐列加（允许失败，列已存在时跳过）：

```
source                 TEXT DEFAULT 'explicit'
status                 TEXT DEFAULT 'active'
evidence               TEXT DEFAULT ''
source_conversation_id INTEGER
source_message_ids     TEXT DEFAULT '[]'
valid_from             TEXT
valid_to               TEXT
last_seen_at           TEXT
seen_count             INTEGER DEFAULT 1
```

## 四、文件变更清单

| 文件 | 操作 | 内容 |
|------|------|------|
| `memory/schema.sql` | 改 | 新增 memory_candidates 表 |
| `memory/sqlite_store.py` | 改 | _migrate_db() + save_memory 扩展 + 5 新方法 |
| `config/settings.py` | 改 | passive_memory_enabled: bool = True |
| `memory/prompts.py` | 新建 | 提取 prompt |
| `memory/passive_extractor.py` | 新建 | 调度 + 提取管线 |
| `app/main.py` | 改 | 触发点 + 3 端点 |
| `static/index.html` | 改 | 前端候选 UI |
| `tests/test_passive_memory_schema.py` | 新建 | schema 测试 |
| `tests/test_passive_memory_candidates.py` | 新建 | CRUD 测试 |
| `tests/test_passive_memory_api.py` | 新建 | API 测试 |
| `tests/test_passive_memory_extractor.py` | 新建 | 提取器测试 |

---

## 五、详细实施步骤

---

### Step 1：schema.sql — 新增 memory_candidates 表

**文件：** `memory/schema.sql`

在文件末尾（`document_updates` 表之后）追加：

```sql
-- ═══════════════════════════════════════════
-- 被动记忆候选表：后台提取、用户审核
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS memory_candidates (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    key                     TEXT    NOT NULL,
    value                   TEXT    NOT NULL,
    category                TEXT    DEFAULT '',
    confidence              REAL    DEFAULT 0.5,
    importance              REAL    DEFAULT 0.5,
    sensitivity             TEXT    DEFAULT 'low',
    action                  TEXT    DEFAULT 'store',
    evidence                TEXT    DEFAULT '',
    reason                  TEXT    DEFAULT '',
    source_conversation_id  INTEGER,
    source_message_ids      TEXT    DEFAULT '[]',
    status                  TEXT    DEFAULT 'pending',
    created_at              TEXT    DEFAULT (datetime('now','localtime')),
    reviewed_at             TEXT
);
```

---

### Step 2：sqlite_store.py — 核心改动

**文件：** `memory/sqlite_store.py`

#### 2a. 新增 `_migrate_db()` 方法

在 `_init_db()` 方法的 `conn.executescript(...)` 之后加一行调用：

```python
def _init_db(self):
    """初始化数据库：创建表结构"""
    schema_path = Path(__file__).parent / "schema.sql"
    with self._connect() as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
    self._migrate_db()  # ← 新增这一行


def _migrate_db(self):
    """给旧数据库补加新列，列已存在则跳过"""
    import sqlite3 as _sqlite3
    migrations = [
        "ALTER TABLE memories ADD COLUMN source TEXT DEFAULT 'explicit'",
        "ALTER TABLE memories ADD COLUMN status TEXT DEFAULT 'active'",
        "ALTER TABLE memories ADD COLUMN evidence TEXT DEFAULT ''",
        "ALTER TABLE memories ADD COLUMN source_conversation_id INTEGER",
        "ALTER TABLE memories ADD COLUMN source_message_ids TEXT DEFAULT '[]'",
        "ALTER TABLE memories ADD COLUMN valid_from TEXT",
        "ALTER TABLE memories ADD COLUMN valid_to TEXT",
        "ALTER TABLE memories ADD COLUMN last_seen_at TEXT",
        "ALTER TABLE memories ADD COLUMN seen_count INTEGER DEFAULT 1",
    ]
    with self._connect() as conn:
        for sql in migrations:
            try:
                conn.execute(sql)
            except _sqlite3.OperationalError:
                pass  # 列已存在，跳过
```

#### 2b. 扩展 `save_memory()` 签名

把原来的：

```python
def save_memory(self, key: str, value: str, category: str = "") -> dict:
```

改成（所有新参数有默认值，旧调用完全兼容）：

```python
def save_memory(self, key: str, value: str, category: str = "",
                confidence: float = 1.0, source: str = "explicit",
                evidence: str = "",
                source_conversation_id: int | None = None,
                source_message_ids: str | None = None,
                seen_count: int = 1) -> dict:
    """保存一条长期记忆，key 重复则更新。

    新增参数全部带默认值，旧的 save_memory("k","v","cat") 行为不变。
    """
    source_message_ids = source_message_ids or '[]'
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    with self._connect() as conn:
        conn.execute("""
            INSERT INTO memories (
                key, value, category, confidence, source, status,
                evidence, source_conversation_id, source_message_ids,
                last_seen_at, seen_count, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                category = excluded.category,
                confidence = excluded.confidence,
                updated_at = excluded.updated_at,
                last_seen_at = excluded.last_seen_at,
                seen_count = memories.seen_count + 1
            """, (
                key, value, category, confidence, source, evidence,
                source_conversation_id, source_message_ids,
                now, seen_count, now,
            ))
    return self.get_memory(key)
```

> **兼容性：** 旧调用 `save_memory("k", "v", "cat")` 走 `confidence=1.0, source='explicit'`，和以前完全一致。各工具测试 mock 都用 3 个位置参数，不会受影响。

#### 2c. 新增 5 个方法

在 `get_recent_conversations` 方法之后追加：

```python
def get_recent_messages(self, conversation_id: int, limit: int = 12) -> list[dict]:
    """取某个会话最近 N 条消息，返回时间正序（旧→新）"""
    with self._connect() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (conversation_id, limit)
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def insert_memory_candidate(self, key: str, value: str,
                             category: str = "",
                             confidence: float = 0.5,
                             importance: float = 0.5,
                             sensitivity: str = "low",
                             action: str = "store",
                             evidence: str = "",
                             reason: str = "",
                             source_conversation_id: int | None = None,
                             source_message_ids: str = "[]",
                             status: str = "pending") -> int:
    """插入一条候选记忆，返回 id"""
    with self._connect() as conn:
        cursor = conn.execute(
            "INSERT INTO memory_candidates ("
            "key, value, category, confidence, importance, sensitivity, "
            "action, evidence, reason, source_conversation_id, "
            "source_message_ids, status"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (key, value, category, confidence, importance, sensitivity,
             action, evidence, reason, source_conversation_id,
             source_message_ids, status)
        )
        return cursor.lastrowid


def list_memory_candidates(self, status: str = "pending") -> list[dict]:
    """列出候选记忆，按状态筛选"""
    with self._connect() as conn:
        rows = conn.execute(
            "SELECT * FROM memory_candidates WHERE status = ? "
            "ORDER BY created_at DESC",
            (status,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_memory_candidate(self, candidate_id: int) -> dict | None:
    """查一条候选记忆"""
    with self._connect() as conn:
        row = conn.execute(
            "SELECT * FROM memory_candidates WHERE id = ?",
            (candidate_id,)
        ).fetchone()
        return dict(row) if row else None


def update_memory_candidate_status(self, candidate_id: int,
                                    status: str) -> bool:
    """更新候选状态，自动写入 reviewed_at"""
    reviewed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    with self._connect() as conn:
        cursor = conn.execute(
            "UPDATE memory_candidates SET status = ?, reviewed_at = ? "
            "WHERE id = ?",
            (status, reviewed_at, candidate_id)
        )
        return cursor.rowcount > 0
```

---

### Step 3：settings.py — 开关

**文件：** `config/settings.py`

在 Settings 类里加一行（比如放在 reflexion_min_score 下面）：

```python
# Passive memory extraction
passive_memory_enabled: bool = True
```

.env 里可以设 `PASSIVE_MEMORY_ENABLED=false` 关闭。

---

### Step 4：memory/prompts.py — 提取 prompt

**新建文件：** `memory/prompts.py`

```python
# memory/prompts.py
# Passive memory extraction prompt templates


EXTRACTION_SYSTEM_PROMPT = """You are a "personal memory assistant". Your job is to read conversations between a user and an AI assistant, and extract stable facts, preferences, and knowledge about the user that are worth remembering long-term.

Rules:
1. Only extract facts the USER explicitly stated or confirmed. Do NOT extract facts stated only by the assistant.
2. Do NOT extract one-time questions (e.g. "What is Redis default port?").
3. Do NOT extract temporary states ("I'm tired today").
4. Do NOT extract passwords, API keys, tokens, ID numbers, bank cards, exact addresses.
5. Categorize each fact:
   - "preference": user likes/dislikes, habits, preferences
   - "tech_stack": programming languages, frameworks, tools the user uses
   - "project": projects the user is working on
   - "workflow": how the user works, workflow preferences
   - "constraint": constraints or requirements the user has
   - "fact": general facts about the user
6. Assign confidence (0.0-1.0):
   - 0.9-1.0: user explicitly stated a long-term fact ("I use Python 3.11")
   - 0.7-0.89: strongly implied but not a direct statement
   - 0.5-0.69: possibly useful, needs confirmation
   - <0.5: do NOT include — skip entirely
7. Assign importance (0.0-1.0): how often this fact might affect future conversations.
8. Assign sensitivity:
   - "low": public info or general preference
   - "medium": personal preference or project detail
   - "high": private detail, should NOT be auto-saved
9. Set action:
   - "store": save this as a new memory
   - "forget": skip (use this for anything not worth remembering)

Return ONLY valid JSON. Do NOT include markdown code blocks or any text outside the JSON.

JSON format:
{
    "memories": [
        {
            "key": "snake_case_identifier",
            "value": "self-contained sentence",
            "category": "preference",
            "confidence": 0.9,
            "importance": 0.8,
            "sensitivity": "low",
            "action": "store",
            "evidence": "exact user quote from the conversation",
            "reason": "why this is worth remembering"
        }
    ]
}

If nothing is worth remembering, return {"memories": []}."""


EXTRACTION_USER_PROMPT = """Analyze this conversation and extract user facts worth remembering:

{conversation_text}

Return only the JSON object."""


def build_extraction_prompt(conversation_text: str) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the extraction LLM call."""
    return EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_PROMPT.format(
        conversation_text=conversation_text
    )
```

---

### Step 5：memory/passive_extractor.py — 提取管线

**新建文件：** `memory/passive_extractor.py`

```python
# memory/passive_extractor.py
# Passive memory extraction — scheduling + extraction pipeline
#
# Design:
#   - threading.Timer for debounced scheduling (sync route → no asyncio loop)
#   - All exceptions caught silently → never affects main chat path
#   - All candidates go to "pending" status in Phase 1

import json
import re
import threading
from typing import Optional


# ── Scheduling (debounced) ──────────────────────────────────────────

_pending_timers: dict[int, threading.Timer] = {}


def schedule_passive_memory_extraction(conversation_id: int,
                                        delay_seconds: int = 120) -> None:
    """Schedule passive memory extraction after a delay.

    If a timer is already pending for this conversation, cancel it
    and start a new one (debounce). Runs in a daemon thread so it
    never blocks the main chat path.
    """
    from config.settings import settings
    if not settings.passive_memory_enabled:
        return

    if conversation_id in _pending_timers:
        _pending_timers[conversation_id].cancel()

    timer = threading.Timer(delay_seconds, extract_passive_memories,
                            args=[conversation_id])
    timer.daemon = True
    timer.start()
    _pending_timers[conversation_id] = timer


# ── Helpers ─────────────────────────────────────────────────────────

def _format_messages(messages: list[dict]) -> str:
    """Format messages into a readable conversation transcript."""
    lines = []
    for m in messages:
        role_label = "User" if m["role"] == "user" else "Assistant"
        lines.append(f"[{role_label}]: {m['content']}")
    return "\n\n".join(lines)


def _extract_json(text: str) -> Optional[dict]:
    """Extract JSON from LLM output with 3 fallback layers.

    Same pattern as agent/reflexion.py's _extract_json.
    """
    if not text or not isinstance(text, str):
        return None

    # Layer 1: direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Layer 2: ```json ... ``` code block
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # Layer 3: outermost { ... }
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    return None


# ── Main extraction ─────────────────────────────────────────────────

def extract_passive_memories(conversation_id: int) -> None:
    """Read recent messages, call LLM, insert pending candidates.

    All exceptions are caught silently — failure here must NEVER
    affect the main chat path.
    """
    try:
        from memory.sqlite_store import get_store
        from memory.prompts import build_extraction_prompt
        from llm.ollama_client import get_ollama_client
        from config.settings import settings

        store = get_store()

        # 1. Read recent messages
        messages = store.get_recent_messages(conversation_id, limit=12)
        if not messages:
            return

        # 2. Build prompt
        conversation_text = _format_messages(messages)
        system_prompt, user_prompt = build_extraction_prompt(conversation_text)

        # 3. Call LLM
        client = get_ollama_client()
        response = client.chat(
            model=settings.ollama_chat_model,
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt,
        )

        # 4. Parse response
        result = _extract_json(response)
        if not result:
            return

        candidates = result.get("memories", [])
        if not isinstance(candidates, list):
            return

        # 5. Insert pending candidates
        source_message_ids = json.dumps([m["id"] for m in messages])
        for c in candidates:
            action = c.get("action", "store")
            if action == "forget":
                continue

            store.insert_memory_candidate(
                key=str(c.get("key", "")).strip(),
                value=str(c.get("value", "")).strip(),
                category=str(c.get("category", "")).strip(),
                confidence=float(c.get("confidence", 0.5)),
                importance=float(c.get("importance", 0.5)),
                sensitivity=str(c.get("sensitivity", "low")),
                action=action,
                evidence=str(c.get("evidence", "")).strip(),
                reason=str(c.get("reason", "")).strip(),
                source_conversation_id=conversation_id,
                source_message_ids=source_message_ids,
                status="pending",
            )

    except Exception:
        # Extraction failure must never propagate to the chat path
        pass
```

---

### Step 6：app/main.py — 触发点

**文件：** `app/main.py`

在 `save_message` 函数的 `store.save_message(...)` 和 `return` 之间加 3 行：

```python
@app.post("/conversations/{conv_id}/messages")
def save_message(conv_id: int, req: SaveMessageRequest):
    """向会话追加一条消息"""
    store = get_store()
    conv = store.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    store.save_message(conv_id, req.role, req.content)

    # 被动记忆提取：assistant 消息落库后触发后台提取
    if req.role == "assistant":
        from memory.passive_extractor import schedule_passive_memory_extraction
        schedule_passive_memory_extraction(conv_id)

    return {"status": "ok"}
```

---

### Step 7：app/main.py — 3 个新端点

**文件：** `app/main.py`

在文件末尾（`if __name__ == "__main__"` 之前，紧跟最后一个已有路由之后）追加：

```python
# ═══════════════════════════════════════════════
# 被动记忆提取 — 候选审核
# ═══════════════════════════════════════════════

@app.get("/memory/candidates")
def list_memory_candidates(status: str = "pending"):
    """列出候选记忆"""
    store = get_store()
    candidates = store.list_memory_candidates(status)
    return {"candidates": candidates}


@app.post("/memory/candidates/{candidate_id}/accept")
def accept_memory_candidate(candidate_id: int):
    """接受一条候选 → 写入正式记忆"""
    store = get_store()
    candidate = store.get_memory_candidate(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate["status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Candidate already {candidate['status']}"
        )

    store.save_memory(
        key=candidate["key"],
        value=candidate["value"],
        category=candidate["category"],
        confidence=candidate["confidence"],
        source="passive",
        evidence=candidate["evidence"],
        source_conversation_id=candidate["source_conversation_id"],
        source_message_ids=candidate["source_message_ids"],
        seen_count=1,
    )
    store.update_memory_candidate_status(candidate_id, "accepted")

    return {"status": "ok", "message": f"已记住：{candidate['key']}"}


@app.post("/memory/candidates/{candidate_id}/reject")
def reject_memory_candidate(candidate_id: int):
    """拒绝一条候选"""
    store = get_store()
    candidate = store.get_memory_candidate(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate["status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Candidate already {candidate['status']}"
        )

    store.update_memory_candidate_status(candidate_id, "rejected")
    return {"status": "ok", "message": f"已拒绝：{candidate['key']}"}
```

---

### Step 8：static/index.html — 前端 UI

**文件：** `static/index.html`

#### 8a. CSS

在 `<style>` 块末尾（`</style>` 之前）追加：

```css
/* 被动记忆候选区域 */
.candidate-section { margin-top: 16px; border-top: 1px solid #e0e0e0; padding-top: 12px; }
.candidate-item { padding: 8px 10px; margin-bottom: 6px; border-radius: 6px; background: #fffef5; border: 1px solid #f0e8c0; font-size: 12px; }
.candidate-key { font-weight: 600; color: #2c3e50; font-size: 13px; margin-bottom: 2px; }
.candidate-value { color: #555; margin-bottom: 4px; }
.candidate-meta { color: #999; font-size: 11px; margin-bottom: 2px; }
.candidate-meta span { margin-right: 8px; }
.candidate-actions { display: flex; gap: 4px; margin-top: 6px; }
.candidate-actions button { padding: 3px 12px; font-size: 11px; border-radius: 4px; cursor: pointer; border: none; color: #fff; }
.btn-accept { background: #27ae60; }
.btn-accept:hover { background: #2ecc71; }
.btn-reject { background: #c0392b; }
.btn-reject:hover { background: #e74c3c; }
```

#### 8b. HTML

在侧边栏中 `#conversationList` 之后追加（约第 150 行附近，在实际的 `</div>` 关闭侧边栏 `#sidebar` 之前）：

```html
<div class="candidate-section" id="candidateSection" style="display:none">
  <div style="font-weight:600;margin-bottom:6px;color:#555;font-size:13px">
    待确认记忆 (<span id="candidateCount">0</span>)
  </div>
  <div id="candidateList"></div>
</div>
```

#### 8c. JavaScript

在 `<script>` 块内追加以下函数（放在现有其他函数后面即可）：

```javascript
async function loadCandidates() {
  try {
    var r = await fetch('/memory/candidates?status=pending');
    var d = await r.json();
    var candidates = d.candidates || [];
    var section = document.getElementById('candidateSection');
    var countEl = document.getElementById('candidateCount');
    var listEl = document.getElementById('candidateList');

    countEl.textContent = candidates.length;
    section.style.display = candidates.length > 0 ? 'block' : 'none';

    if (candidates.length === 0) {
      listEl.innerHTML = '';
      return;
    }

    listEl.innerHTML = candidates.map(function(c) {
      var confPct = (c.confidence * 100).toFixed(0);
      return '<div class="candidate-item">'
        + '<div class="candidate-key">' + escHtml(c.key) + '</div>'
        + '<div class="candidate-value">' + escHtml(c.value) + '</div>'
        + '<div class="candidate-meta">'
        + '<span>分类: ' + escHtml(c.category || '') + '</span>'
        + '<span>置信度: ' + confPct + '%</span>'
        + '</div>'
        + (c.evidence ? '<div class="candidate-meta">证据: ' + escHtml(c.evidence.slice(0, 80)) + '</div>' : '')
        + '<div class="candidate-actions">'
        + '<button class="btn-accept" onclick="acceptCandidate(' + c.id + ')">接受</button>'
        + '<button class="btn-reject" onclick="rejectCandidate(' + c.id + ')">拒绝</button>'
        + '</div>'
        + '</div>';
    }).join('');
  } catch(e) {
    console.error('loadCandidates failed:', e);
  }
}

async function acceptCandidate(id) {
  try {
    await fetch('/memory/candidates/' + id + '/accept', {method: 'POST'});
    loadCandidates();
    loadMemories();  // 刷新正式记忆面板
  } catch(e) {
    alert('接受失败: ' + e.message);
  }
}

async function rejectCandidate(id) {
  try {
    await fetch('/memory/candidates/' + id + '/reject', {method: 'POST'});
    loadCandidates();
  } catch(e) {
    alert('拒绝失败: ' + e.message);
  }
}

function escHtml(str) {
  var d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}
```

#### 8d. 调用时机

在页面加载处（现有 `loadConversations()` 调用附近）加上：

```javascript
loadCandidates();
```

在 `switchTab` 函数中，切换到 chat tab 时加上：

```javascript
if (name === 'chat') {
  sidebar.classList.add('show');
  loadCandidates();  // ← 新增
}
```

---

### Step 9：测试

新建 4 个测试文件。

#### 9a. tests/test_passive_memory_schema.py

```python
"""Test that memory_candidates table and new memories columns exist."""
import pytest
from pathlib import Path
from memory.sqlite_store import SqliteStore


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    return SqliteStore(tmp_path / "test.db")


class TestMemoryCandidatesTable:
    def test_table_exists(self, store):
        with store._connect() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='memory_candidates'"
            ).fetchone()
            assert row is not None

    def test_required_columns_present(self, store):
        with store._connect() as conn:
            rows = conn.execute("PRAGMA table_info(memory_candidates)").fetchall()
            cols = {r["name"] for r in rows}
        expected = {"id", "key", "value", "category", "confidence",
                    "importance", "sensitivity", "action", "evidence",
                    "reason", "source_conversation_id", "source_message_ids",
                    "status", "created_at", "reviewed_at"}
        assert expected.issubset(cols)

    def test_default_status_is_pending(self, store):
        cid = store.insert_memory_candidate("k", "v")
        c = store.get_memory_candidate(cid)
        assert c["status"] == "pending"


class TestMemoriesMigration:
    def test_new_columns_exist(self, store):
        with store._connect() as conn:
            rows = conn.execute("PRAGMA table_info(memories)").fetchall()
            cols = {r["name"] for r in rows}
        expected = {"source", "status", "evidence",
                    "source_conversation_id", "source_message_ids",
                    "valid_from", "valid_to", "last_seen_at", "seen_count"}
        assert expected.issubset(cols)

    def test_migration_idempotent(self, store):
        """Calling migration again should not raise."""
        store._migrate_db()  # should not throw
```

#### 9b. tests/test_passive_memory_candidates.py

```python
"""Test memory candidate CRUD operations."""
import pytest
from pathlib import Path
from memory.sqlite_store import SqliteStore


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    return SqliteStore(tmp_path / "test.db")


class TestCandidateCRUD:
    def test_insert_returns_id(self, store):
        cid = store.insert_memory_candidate("k1", "v1")
        assert isinstance(cid, int)
        assert cid > 0

    def test_get_candidate(self, store):
        cid = store.insert_memory_candidate("k1", "v1", category="pref")
        c = store.get_memory_candidate(cid)
        assert c["key"] == "k1"
        assert c["value"] == "v1"
        assert c["category"] == "pref"

    def test_get_nonexistent(self, store):
        assert store.get_memory_candidate(99999) is None

    def test_list_pending_only(self, store):
        store.insert_memory_candidate("a", "va", status="pending")
        store.insert_memory_candidate("b", "vb", status="pending")
        store.insert_memory_candidate("c", "vc", status="accepted")
        assert len(store.list_memory_candidates("pending")) == 2
        assert len(store.list_memory_candidates("accepted")) == 1

    def test_list_empty(self, store):
        assert store.list_memory_candidates("pending") == []

    def test_update_status(self, store):
        cid = store.insert_memory_candidate("k", "v")
        assert store.update_memory_candidate_status(cid, "accepted") is True
        c = store.get_memory_candidate(cid)
        assert c["status"] == "accepted"
        assert c["reviewed_at"] is not None

    def test_update_nonexistent(self, store):
        assert store.update_memory_candidate_status(99999, "accepted") is False

    def test_default_status_is_pending(self, store):
        cid = store.insert_memory_candidate("k", "v")
        assert store.get_memory_candidate(cid)["status"] == "pending"

    def test_all_fields_preserved(self, store):
        cid = store.insert_memory_candidate(
            key="test_key", value="test_value", category="tech_stack",
            confidence=0.85, importance=0.7, sensitivity="low",
            action="store", evidence="user said it", reason="useful",
            source_conversation_id=3,
            source_message_ids="[1,2]", status="pending",
        )
        c = store.get_memory_candidate(cid)
        assert c["confidence"] == 0.85
        assert c["importance"] == 0.7
        assert c["evidence"] == "user said it"
        assert c["source_conversation_id"] == 3


class TestSaveMemoryBackwardCompat:
    def test_old_signature_works(self, store):
        """save_memory("k","v","cat") must still work."""
        m = store.save_memory("key1", "value1", "cat1")
        assert m["key"] == "key1"
        assert m["value"] == "value1"
        assert m["category"] == "cat1"

    def test_default_confidence_is_1(self, store):
        m = store.save_memory("key1", "value1")
        assert m["confidence"] == 1.0

    def test_default_source_is_explicit(self, store):
        m = store.save_memory("key1", "value1")
        assert m["source"] == "explicit"

    def test_new_params_accepted(self, store):
        m = store.save_memory("key1", "value1", "cat1",
                               confidence=0.8, source="passive",
                               evidence="test ev", seen_count=3)
        assert m["confidence"] == 0.8
        assert m["source"] == "passive"
        assert m["evidence"] == "test ev"
```

#### 9c. tests/test_passive_memory_api.py

```python
"""Test passive memory API endpoints."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestListCandidates:
    def test_list_pending(self, client):
        mock = MagicMock()
        mock.list_memory_candidates.return_value = [
            {"id": 1, "key": "k1", "value": "v1", "status": "pending"},
        ]
        with patch("app.main.get_store", return_value=mock):
            resp = client.get("/memory/candidates?status=pending")
            assert resp.status_code == 200
            assert len(resp.json()["candidates"]) == 1

    def test_list_empty(self, client):
        mock = MagicMock()
        mock.list_memory_candidates.return_value = []
        with patch("app.main.get_store", return_value=mock):
            resp = client.get("/memory/candidates")
            assert resp.status_code == 200
            assert resp.json()["candidates"] == []


class TestAcceptCandidate:
    def test_accept_success(self, client):
        mock = MagicMock()
        mock.get_memory_candidate.return_value = {
            "id": 1, "key": "k1", "value": "v1", "category": "pref",
            "confidence": 0.9, "evidence": "ev", "status": "pending",
            "source_conversation_id": 1, "source_message_ids": "[1]",
        }
        with patch("app.main.get_store", return_value=mock):
            resp = client.post("/memory/candidates/1/accept")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
            mock.save_memory.assert_called_once()
            mock.update_memory_candidate_status.assert_called_once_with(
                1, "accepted")

    def test_accept_not_found(self, client):
        mock = MagicMock()
        mock.get_memory_candidate.return_value = None
        with patch("app.main.get_store", return_value=mock):
            resp = client.post("/memory/candidates/999/accept")
            assert resp.status_code == 404

    def test_accept_already_processed(self, client):
        mock = MagicMock()
        mock.get_memory_candidate.return_value = {
            "id": 1, "key": "k1", "value": "v1", "status": "accepted",
        }
        with patch("app.main.get_store", return_value=mock):
            resp = client.post("/memory/candidates/1/accept")
            assert resp.status_code == 400


class TestRejectCandidate:
    def test_reject_success(self, client):
        mock = MagicMock()
        mock.get_memory_candidate.return_value = {
            "id": 1, "key": "k1", "value": "v1", "status": "pending",
        }
        with patch("app.main.get_store", return_value=mock):
            resp = client.post("/memory/candidates/1/reject")
            assert resp.status_code == 200
            mock.update_memory_candidate_status.assert_called_once_with(
                1, "rejected")

    def test_reject_not_found(self, client):
        mock = MagicMock()
        mock.get_memory_candidate.return_value = None
        with patch("app.main.get_store", return_value=mock):
            resp = client.post("/memory/candidates/999/reject")
            assert resp.status_code == 404
```

#### 9d. tests/test_passive_memory_extractor.py

```python
"""Test passive memory extraction logic (LLM mocked)."""
import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from memory.sqlite_store import SqliteStore


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    return SqliteStore(tmp_path / "test.db")


class TestFormatMessages:
    def test_format(self):
        from memory.passive_extractor import _format_messages
        msgs = [
            {"id": 1, "role": "user", "content": "Hello"},
            {"id": 2, "role": "assistant", "content": "Hi"},
        ]
        result = _format_messages(msgs)
        assert "[User]: Hello" in result
        assert "[Assistant]: Hi" in result

    def test_empty(self):
        from memory.passive_extractor import _format_messages
        assert _format_messages([]) == ""


class TestExtractJson:
    def test_direct_json(self):
        from memory.passive_extractor import _extract_json
        assert _extract_json('{"a": 1}') == {"a": 1}

    def test_code_block(self):
        from memory.passive_extractor import _extract_json
        result = _extract_json('```json\n{"a": 1}\n```')
        assert result == {"a": 1}

    def test_braced_json(self):
        from memory.passive_extractor import _extract_json
        result = _extract_json('some text {"a": 1} more text')
        assert result == {"a": 1}

    def test_invalid(self):
        from memory.passive_extractor import _extract_json
        assert _extract_json("not json") is None
        assert _extract_json("") is None
        assert _extract_json(None) is None


class TestExtractionPipeline:
    def test_extracts_candidates(self, store):
        from memory.passive_extractor import extract_passive_memories

        conv_id = store.create_conversation("test")
        store.save_message(conv_id, "user", "My name is Xiao Ming")
        store.save_message(conv_id, "assistant", "Hello Xiao Ming")
        store.save_message(conv_id, "user", "I use Python for all my projects")

        mock_response = json.dumps({
            "memories": [
                {"key": "user_name", "value": "Xiao Ming",
                 "category": "personal", "confidence": 0.95,
                 "importance": 0.8, "sensitivity": "medium",
                 "action": "store",
                 "evidence": "My name is Xiao Ming",
                 "reason": "User identity"},
                {"key": "tech_stack_python", "value": "Python",
                 "category": "tech_stack", "confidence": 0.9,
                 "importance": 0.85, "sensitivity": "low",
                 "action": "store",
                 "evidence": "I use Python for all my projects",
                 "reason": "Tech stack"},
            ]
        })

        mock_client = MagicMock()
        mock_client.chat.return_value = mock_response

        with patch("memory.passive_extractor.get_store", return_value=store):
            with patch("memory.passive_extractor.get_ollama_client",
                       return_value=mock_client):
                extract_passive_memories(conv_id)

        pending = store.list_memory_candidates("pending")
        assert len(pending) == 2
        assert all(c["status"] == "pending" for c in pending)

    def test_skips_forget_actions(self, store):
        from memory.passive_extractor import extract_passive_memories

        conv_id = store.create_conversation("test")
        store.save_message(conv_id, "user", "blah")

        mock_response = json.dumps({
            "memories": [
                {"key": "skip", "value": "x", "action": "forget",
                 "confidence": 0.5, "importance": 0.5},
                {"key": "keep", "value": "y", "action": "store",
                 "confidence": 0.5, "importance": 0.5},
            ]
        })
        mock_client = MagicMock()
        mock_client.chat.return_value = mock_response

        with patch("memory.passive_extractor.get_store", return_value=store):
            with patch("memory.passive_extractor.get_ollama_client",
                       return_value=mock_client):
                extract_passive_memories(conv_id)

        pending = store.list_memory_candidates("pending")
        assert len(pending) == 1
        assert pending[0]["key"] == "keep"

    def test_empty_response(self, store):
        from memory.passive_extractor import extract_passive_memories

        conv_id = store.create_conversation("test")
        store.save_message(conv_id, "user", "OK")

        mock_response = json.dumps({"memories": []})
        mock_client = MagicMock()
        mock_client.chat.return_value = mock_response

        with patch("memory.passive_extractor.get_store", return_value=store):
            with patch("memory.passive_extractor.get_ollama_client",
                       return_value=mock_client):
                extract_passive_memories(conv_id)

        assert store.list_memory_candidates("pending") == []

    def test_llm_error_graceful(self, store):
        from memory.passive_extractor import extract_passive_memories

        conv_id = store.create_conversation("test")
        store.save_message(conv_id, "user", "Hello")

        mock_client = MagicMock()
        mock_client.chat.side_effect = RuntimeError("Ollama down")

        with patch("memory.passive_extractor.get_store", return_value=store):
            with patch("memory.passive_extractor.get_ollama_client",
                       return_value=mock_client):
                extract_passive_memories(conv_id)  # must not raise

        assert store.list_memory_candidates("pending") == []

    def test_no_messages_skips(self, store):
        from memory.passive_extractor import extract_passive_memories

        conv_id = store.create_conversation("test")
        # no messages

        mock_client = MagicMock()
        with patch("memory.passive_extractor.get_store", return_value=store):
            with patch("memory.passive_extractor.get_ollama_client",
                       return_value=mock_client):
                extract_passive_memories(conv_id)

        mock_client.chat.assert_not_called()


class TestScheduling:
    def test_schedule_creates_timer(self):
        from memory.passive_extractor import (
            schedule_passive_memory_extraction, _pending_timers)
        _pending_timers.clear()
        schedule_passive_memory_extraction(1, delay_seconds=0)
        assert 1 in _pending_timers
        _pending_timers[1].cancel()

    def test_schedule_debounces(self):
        from memory.passive_extractor import (
            schedule_passive_memory_extraction, _pending_timers)
        _pending_timers.clear()
        schedule_passive_memory_extraction(1, delay_seconds=60)
        first = _pending_timers[1]
        schedule_passive_memory_extraction(1, delay_seconds=60)
        second = _pending_timers[1]
        assert second is not first
        second.cancel()

    def test_disabled_when_false(self):
        from memory.passive_extractor import (
            schedule_passive_memory_extraction, _pending_timers)
        from config.settings import settings

        _pending_timers.clear()
        original = settings.passive_memory_enabled
        settings.passive_memory_enabled = False
        try:
            schedule_passive_memory_extraction(1)
            assert 1 not in _pending_timers
        finally:
            settings.passive_memory_enabled = original
```

---

### Step 10：回归验证

```bash
pytest tests/ -v
```

确保 318 个已有测试全部通过，且新增的 4 个测试文件也全部通过。

每个新建测试文件独立运行验证：

```bash
pytest tests/test_passive_memory_schema.py -v
pytest tests/test_passive_memory_candidates.py -v
pytest tests/test_passive_memory_api.py -v
pytest tests/test_passive_memory_extractor.py -v
```

---

## 六、全局手动验证流程

1. 启动服务：`uvicorn app.main:app --reload`
2. 浏览器打开 `http://127.0.0.1:8000`
3. 在聊天界面发几条包含个人信息的话：
   > 我叫张三，平时主要写 Python 和 Go。
   > 我的项目 private-agent 是一个本地知识管家。
4. 等待 120 秒（测试时可以临时把 `delay_seconds` 改成 5 秒）
5. 刷新页面，侧边栏应出现 `待确认记忆 (N)`
6. 点击候选上的 **接受** → 切换到记忆面板能看到这条记忆
7. 点击候选上的 **拒绝** → 候选消失
8. 在 .env 设置 `PASSIVE_MEMORY_ENABLED=false`，重启，新的对话不再产生候选

---

## 七、风险与缓解

| 风险 | 缓解 |
|------|------|
| ALTER TABLE 重复执行报错 | try/except OperationalError |
| Qwen 输出非 JSON | 3 层 _extract_json 容错 |
| 提取在 daemon 线程中报错 | 整个 extract 包在 try/except 中 |
| threading.Timer 在主线程退出后被强制终止 | daemon=True，不影响进程退出 |
| 旧测试因新列而失败 | 新列都有 DEFAULT，旧测试不检查这些列 |
| save_memory mock 参数不匹配 | 新参数全是 keyword 默认值，旧 position arg mock 不受影响 |

---

## 八、Phase 2 路线图

> 评审日期：2026-07-01
> 评审来源：外部 LLM（GPT）对 Phase 1 完成后的方向评审

### 8.1 核心思路

Phase 1 已经把"生产管线"打通了，Phase 2 的核心不是再做一条管线，而是解决：

> **这些 memory candidates 如何真正进入"可用状态"，并开始影响回答质量，而不引入污染和延迟。**

### 8.2 推荐实施顺序

| 优先级 | 功能 | 说明 |
|--------|------|------|
| 第 1 | **读路径注入（Read-path injection）** | 让记忆被用起来，哪怕还不完美 |
| 第 2 | **极保守 auto-accept** | 只处理"几乎确定安全"的子集 |
| 第 3 | **DeepSeek 边界审核** | 作为纠错器，不替代主流程 |
| 第 4 | **历史回填 CLI** | 纯离线能力，最后做 |

### 8.3 第 1 优先：读路径注入

**价值：** 唯一一个直接提升 chat 质量、不依赖候选质量、不改变写路径、不影响现有测试的功能。本质是补上"闭环"——记忆被提取了，但 Agent 还不知道它们存在。

**最小实现：**

```sql
SELECT * FROM memories
WHERE status = 'accepted'
ORDER BY last_seen_at DESC
LIMIT 10
```

先不上 embedding，用 SQLite 直接查，跑通闭环再说。

**必须加的三层过滤：**
1. `status = 'accepted'`（只注入已确认的记忆）
2. `LIMIT 5-10`（防止 token 爆炸）
3. keyword overlap 做 relevance scoring（简单匹配即可）

**关键风险：memory 污染上下文**

如果直接把所有记忆塞 prompt，会干扰 ReAct/Reflexion 决策。解决方案：
- prompt 中明确标注：`treat as hints, not facts`
- 每条记忆带 `source` 和 `evidence`
- feature flag 控制开关

### 8.4 第 2 优先：极保守 auto-accept

**问题：** 原方案 `confidence >= 0.85` 阈值是"假精确"——Qwen2.5:7b 的 confidence 校准不稳定，会迎合 prompt，对模糊事实会高估。

**安全策略（三段式）：**

| 条件 | 动作 |
|------|------|
| `confidence >= 0.95` | auto accept（极少触发） |
| `0.75 ~ 0.95` | pending（默认，人工审核） |
| `< 0.75` | discard（静默丢弃） |

**额外 rule gate：** auto-accept 还需满足：
- `sensitivity != 'high'`
- `category in ["preference", "tech_stack", "project", "workflow"]`（安全分类白名单）
- 不是事实性断言（factual claim，如 "Python 3.11 是最快的版本"）

**最危险的风险：memory 污染**

一旦错误记忆被 auto-accept，它会永久写入 memories、影响所有未来回答。比单次 hallucination 严重得多——因为它是"长期存在"的。

### 8.5 第 3 优先：DeepSeek 边界审核

**定位：** memory adjudicator（记忆裁决者），不是 memory processor（记忆处理器）。

**只在以下情况调用：**
1. 同 key 冲突（新值与旧值矛盾）
2. `importance >= 4` 且 `0.7 <= confidence < 0.9` 的边界候选
3. 用户点了"审核这条记忆"（手动触发）

**注意：** 90% 的候选根本不值得调 DeepSeek。不要放在在线路径上，否则 `/chat/stream` 可能抖动。

### 8.6 第 4 优先：历史回填 CLI

纯离线工具，提升 cold start 时的记忆覆盖率。对当前体验几乎无影响。实现时注意避免 duplicate memory 和 schema drift。

### 8.7 Quick-win 组合（Phase 2 MVP）

```
Step 1: 读路径注入（仅 accepted memories）
  ↓
Step 2: 极保守 auto-accept（>=0.9 + category 白名单）
  ↓
Step 3: logging + metrics（accepted rate / rejected rate / false positive 采样）
```

### 8.8 必须警惕的坑

| 坑 | 严重度 | 缓解 |
|----|--------|------|
| **记忆反向污染** — 模型引用自己之前生成的错误记忆 | 🔴 严重 | prompt 标注 `treat as hints, not facts`；每记忆带 source/evidence |
| **记忆自增强循环** — chat → extraction → injection → chat 行为变化 → extraction 偏移 | 🔴 严重 | freshness decay；`last_seen_at` 权重；限制 top-k |
| **SQLite 并发读写** — `threading.Timer` 写 + `/chat/stream` 读可能冲突 | 🟡 中等 | WAL 模式已缓解；后续考虑 read-only connection |
| **confidence 校准** — Qwen 的 confidence ≠ probability | 🟡 中等 | 不把 confidence 当概率用，只当 heuristic signal |
| **测试稳定性** — injection 改 prompt 可能改变 ReAct 行为 | 🟡 中等 | injection feature flag；auto-accept feature flag |

---

> **设计日期：** 2026-07-01
> **Phase 1 状态：** 已实施
> **Phase 2 状态：** 待规划
