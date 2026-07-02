-- memory/schema.sql
-- SQLite 数据库表结构

-- ═══════════════════════════════════════════
-- 会话表：每次聊天的顶层容器
-- 一个会话包含多条消息（1 对 N 关系）
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,   -- 主键，自动递增（每建一个会话 +1）
    title       TEXT    DEFAULT '新对话',            -- 会话标题，不传时默认为"新对话"
    created_at  TEXT    DEFAULT (datetime('now', 'localtime')),  -- 创建时间，自动填入当前本地时间
    updated_at  TEXT    DEFAULT (datetime('now', 'localtime'))   -- 最后更新时间，发新消息时自动更新
);

-- ═══════════════════════════════════════════
-- 消息表：一条条聊天消息
-- 每条消息属于一个会话（conversations 的子表）
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS messages (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,   -- 主键，自动递增
    conversation_id   INTEGER NOT NULL,                    -- 所属会话 ID（指向 conversations.id）
    role              TEXT    NOT NULL,                     -- 角色：'user'（用户）或 'assistant'（AI）
    content           TEXT    NOT NULL,                     -- 消息内容（正文）
    created_at        TEXT    DEFAULT (datetime('now', 'localtime')),  -- 发送时间
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
    -- ↑ 外键：conversation_id 必须是一个真实存在的会话 ID
    --   ON DELETE CASCADE：删除会话时，它下面的所有消息也自动删除
);

-- ═══════════════════════════════════════════
-- 长期记忆表：用户明确说"记住"的内容
-- 每条记忆用 key 唯一标识，重复保存会覆盖更新
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS memories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,   -- 主键，自动递增
    key         TEXT    UNIQUE NOT NULL,              -- 记忆的标识符，如 'tech_stack'（唯一，不能重复）
    value       TEXT    NOT NULL,                     -- 记忆内容，如 'Java + Spring Boot + Python'
    category    TEXT    DEFAULT '',                       -- 分类：tech_stack（技术栈）| weak_point（薄弱点）| goal（目标）| preference（偏好）
    confidence  REAL    DEFAULT 1.0,                  -- 置信度 0.0~1.0，1.0 = 完全确定
    created_at  TEXT    DEFAULT (datetime('now', 'localtime')),  -- 创建时间
    updated_at  TEXT    DEFAULT (datetime('now', 'localtime'))   -- 最后更新时间
);

-- ═══════════════════════════════════════════
-- 文档来源表：需要监控的 AI 文档源列表
-- 对应 config/sources.yaml 里配置的来源
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS document_sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,   -- 主键
    name            TEXT    NOT NULL,                     -- 来源名称，如 'OpenAI Docs'
    url             TEXT    NOT NULL,                     -- 文档首页 URL
    type            TEXT    DEFAULT 'docs',               -- 类型：docs（文档）| blog（博客）| github（GitHub 仓库）
    tags            TEXT,                                 -- 标签列表，JSON 格式如 '["openai","api"]'
    last_hash       TEXT,                                 -- 上次抓取时的内容哈希值（用于判断是否有更新）
    last_checked_at TEXT,                                 -- 上次检查时间
    created_at      TEXT    DEFAULT (datetime('now', 'localtime'))  -- 首次添加时间
);

-- ═══════════════════════════════════════════
-- 文档更新记录表：每次检测到有更新时记录一条
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS document_updates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,   -- 主键
    source_name TEXT    NOT NULL,                     -- 来源名称（取自 document_sources.name）
    url         TEXT    NOT NULL,                     -- 更新的文档链接
    old_hash    TEXT,                                 -- 旧的内容哈希
    new_hash    TEXT,                                 -- 新的内容哈希（和 old_hash 不同说明有更新）
    summary     TEXT,                                 -- LLM 生成的更新摘要
    relevance   TEXT    DEFAULT 'medium',              -- 对你的相关度：high（高）| medium（中）| low（低）
    created_at  TEXT    DEFAULT (datetime('now', 'localtime'))  -- 发现更新的时间
);

-- ═══════════════════════════════════════════
-- 被动记忆候选表：后台提取、用户审核
-- Phase 1: 所有候选进 pending，不做自动写入
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS memory_candidates (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,   -- 主键，自动递增
    key                     TEXT    NOT NULL,                     -- 记忆标识符，如 'user_language'
    value                   TEXT    NOT NULL,                     -- 记忆内容，如 'Python 3.11'
    category                TEXT    DEFAULT '',                   -- 分类：preference（偏好）| tech_stack（技术栈）| project（项目）| workflow（工作流）| constraint（约束）| fact（事实）
    confidence              REAL    DEFAULT 0.5,                  -- LLM 自评置信度 0.0~1.0，这条事实有多确定是真的
    importance              REAL    DEFAULT 0.5,                  -- LLM 自评重要性 0.0~1.0，这条记忆对未来对话多有用
    sensitivity             TEXT    DEFAULT 'low',                -- 敏感度：low（无害偏好）| medium（个人偏好）| high（隐私，不应自动保存）
    action                  TEXT    DEFAULT 'store',              -- LLM 建议动作：store（保存为候选）| forget（丢弃，不值得记）
    evidence                TEXT    DEFAULT '',                   -- 证据：来自对话原文的短摘录，供用户审核时核实
    reason                  TEXT    DEFAULT '',                   -- LLM 自述：为什么觉得这条值得记住
    source_conversation_id  INTEGER,                              -- 来源会话 ID（对应 conversations.id，知道是哪次聊天提取的）
    source_message_ids      TEXT    DEFAULT '[]',                 -- 来源消息 ID 列表，JSON 数组如 '[1,2,3]'，定位到具体哪几句
    status                  TEXT    DEFAULT 'pending',            -- 审核状态：pending（待确认）| accepted（用户已接受）| rejected（用户已拒绝）| auto_accepted（Phase 2 自动写入）
    created_at              TEXT    DEFAULT (datetime('now','localtime')),  -- 候选创建时间
    reviewed_at             TEXT                                  -- 审核时间（用户点了接受或拒绝才写入，空着表示还没审）
);