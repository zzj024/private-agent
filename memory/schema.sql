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