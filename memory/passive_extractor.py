# memory/passive_extractor.py
# 被动记忆提取 — 调度 + 提取管线
#
# 设计要点：
#   - 用 threading.Timer 做 debounce 调度（触发点是同步路由，拿不到 asyncio loop）
#   - 所有异常静默捕获 → 绝对不影响聊天主路径
#   - Phase 1：所有候选进 pending，不做自动写入

import json
import re
import threading
from typing import Optional


# ── 调度层（debounce）────────────────────────────────────────────────

_pending_timers: dict[int, threading.Timer] = {}


def schedule_passive_memory_extraction(conversation_id: int,
                                        delay_seconds: int = 20) -> None:
    """调度被动记忆提取，延迟若干秒后执行。

    如果同一个会话已经有一个在等待的 timer，取消旧的、启动新的（debounce）。
    timer 是 daemon 线程，不阻塞聊天主路径，主进程退出时自动清理。
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


# ── 工具函数 ─────────────────────────────────────────────────────────

def _normalize_candidates(data: dict) -> list[dict]:
    """将 LLM 的各种自由格式 JSON 转成标准 memories 列表格式。

    小模型（Qwen 2.5 7B）经常忽略 prompt 里要求的格式，返回：
      {"name": "John", "interests": {"language": "Python"}}
    而不是：
      {"memories": [{"key": "name", "value": "John", ...}]}

    这个函数做容错转换。
    """
    memories = []

    def _add(key, value, category="fact", confidence=0.85):
        key = str(key).strip()
        value = str(value).strip()
        if key and value and len(value) > 1:
            memories.append({
                "key": key, "value": value, "category": category,
                "confidence": confidence, "importance": 0.7,
                "sensitivity": "low", "action": "store",
                "evidence": value[:100], "reason": "extracted",
            })

    # 按优先级尝试不同 key
    # 1. "user_info" / "user" 对象
    user = data.get("user_info") or data.get("user") or {}
    if isinstance(user, dict):
        for k, v in user.items():
            if isinstance(v, str):
                _add(k, v)
            elif isinstance(v, dict):
                for sk, sv in v.items():
                    _add(sk, str(sv))

    # 2. 顶层简单 key-value（跳过已知非用户字段）
    skip_keys = {"memories", "user_info", "user", "interests", "preferences"}
    for k, v in data.items():
        if k in skip_keys:
            continue
        if isinstance(v, str):
            _add(k, v)
        elif isinstance(v, (int, float, bool)):
            _add(k, str(v))

    # 3. "interests" / "preferences" 里的嵌套值
    for nest_key in ("interests", "preferences"):
        nested = data.get(nest_key)
        if isinstance(nested, dict):
            for k, v in nested.items():
                _add(k, str(v))

    return memories


def _format_messages(messages: list[dict]) -> str:
    """把消息列表格式化为可读的对话文本"""
    lines = []
    for m in messages:
        role_label = "用户" if m["role"] == "user" else "助手"
        lines.append(f"[{role_label}]: {m['content']}")
    return "\n\n".join(lines)


def _extract_json(text: str) -> Optional[dict]:
    """从 LLM 输出中提取 JSON，三层容错。

    与 agent/reflexion.py 的 _extract_json 逻辑一致。
    """
    if not text or not isinstance(text, str):
        return None

    # 第一层：直接解析
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # 第二层：提取 ```json ... ``` 代码块
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # 第三层：找到最外层的 { ... }
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    return None


# ── 主提取逻辑 ───────────────────────────────────────────────────────

def extract_passive_memories(conversation_id: int) -> None:
    """读取最近消息 → 调 LLM 提取 → 写入 pending 候选。

    所有异常静默捕获 —— 这里的失败绝对不能影响聊天主路径。
    """
    try:
        from memory.sqlite_store import get_store
        from memory.prompts import build_extraction_prompt
        from llm.ollama_client import get_ollama_client
        from config.settings import settings

        store = get_store()

        # 1. 取最近消息
        messages = store.get_recent_messages(conversation_id, limit=12)
        if not messages:
            return

        # 2. 拼 prompt
        conversation_text = _format_messages(messages)
        system_prompt, user_prompt = build_extraction_prompt(conversation_text)

        # 3. 调 LLM（v0.5: 使用统一配置）
        from llm.factory import get_unified_llm
        client = get_unified_llm()
        response = client.chat(
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt,
        )

        # 4. 解析 LLM 返回的 JSON
        result = _extract_json(response)
        if not result:
            return

        # 4b. 格式适配：小模型可能不按格式返回，做容错转换
        candidates = result.get("memories", [])
        if not isinstance(candidates, list) or len(candidates) == 0:
            candidates = _normalize_candidates(result)

        if not candidates:
            return

        # 5. 自动分级写入（v0.5 + 冲突检测）
        source_message_ids = json.dumps([m["id"] for m in messages])
        auto_accept = settings.passive_memory_auto_accept_threshold
        auto_reject = settings.passive_memory_auto_reject_threshold

        accepted_count = 0
        pending_count = 0
        rejected_count = 0
        conflict_count = 0

        # 预加载已有记忆，检测 key 冲突
        existing_memories = {m["key"]: m["value"] for m in store.list_memories()}

        for c in candidates:
            action = c.get("action", "store")
            if action == "forget":
                continue

            key = str(c.get("key", "")).strip()
            value = str(c.get("value", "")).strip()
            category = str(c.get("category", "")).strip()
            confidence = float(c.get("confidence", 0.5))
            importance = float(c.get("importance", 0.5))
            sensitivity = str(c.get("sensitivity", "low"))
            evidence = str(c.get("evidence", "")).strip()
            reason = str(c.get("reason", "")).strip()

            # 冲突检测：key 已存在且值不同 → 强制送审
            old_value = existing_memories.get(key)
            is_conflict = old_value and old_value.strip() != value.strip()

            if is_conflict:
                # 有冲突 → 不论置信度多高，都送审核
                conflict_reason = f"[冲突] 旧值: {old_value} → 新值: {value}"
                store.insert_memory_candidate(
                    key=key, value=value, category=category,
                    confidence=confidence, importance=importance,
                    sensitivity=sensitivity, action=action,
                    evidence=evidence, reason=conflict_reason,
                    source_conversation_id=conversation_id,
                    source_message_ids=source_message_ids,
                    status="pending",
                )
                conflict_count += 1
                pending_count += 1

            elif confidence >= auto_accept:
                # 高可信 + 无冲突 → 直接写入正式记忆
                store.save_memory(
                    key=key, value=value, category=category,
                    confidence=confidence, source="passive",
                    evidence=evidence,
                    source_conversation_id=conversation_id,
                    source_message_ids=source_message_ids,
                    seen_count=1,
                )
                store.insert_memory_candidate(
                    key=key, value=value, category=category,
                    confidence=confidence, importance=importance,
                    sensitivity=sensitivity, action=action,
                    evidence=evidence, reason=reason,
                    source_conversation_id=conversation_id,
                    source_message_ids=source_message_ids,
                    status="auto_accepted",
                )
                accepted_count += 1

            elif confidence >= auto_reject:
                # 中可信 → 人工审核
                store.insert_memory_candidate(
                    key=key, value=value, category=category,
                    confidence=confidence, importance=importance,
                    sensitivity=sensitivity, action=action,
                    evidence=evidence, reason=reason,
                    source_conversation_id=conversation_id,
                    source_message_ids=source_message_ids,
                    status="pending",
                )
                pending_count += 1

            else:
                # 低可信 → 自动丢弃
                store.insert_memory_candidate(
                    key=key, value=value, category=category,
                    confidence=confidence, importance=importance,
                    sensitivity=sensitivity, action=action,
                    evidence=evidence, reason=reason,
                    source_conversation_id=conversation_id,
                    source_message_ids=source_message_ids,
                    status="auto_rejected",
                )
                rejected_count += 1

    except Exception:
        # 提取失败静默丢弃，绝对不影响聊天主路径
        pass
