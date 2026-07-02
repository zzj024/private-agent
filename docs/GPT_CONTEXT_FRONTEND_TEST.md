# 项目上下文报告 — Private Agent 前端功能测试方案

> 自动生成时间：2026-07-02

## 一、项目元信息

- **项目名称**：Private Agent（私人知识库管理员 + 长期记忆系统 + AI 助手）
- **技术栈**：Python 3.11 / FastAPI / LangGraph / SQLite / ChromaDB / Ollama (Qwen 2.5 7B + nomic-embed-text) / Vanilla JS 单文件前端
- **前端**：`static/index.html`，1549 行，无框架，marked + DOMPurify 渲染 Markdown，SSE 流式接收
- **后端**：FastAPI，端口 8000，约 30 个 API 端点
- **数据库**：SQLite (agent.db) + ChromaDB (data/chroma/)
- **测试文档**：目前有 test_knowledge_api.py (13 个新测试)、test_passive_memory_api.py (7 个)、等共 367 个后端测试
- **本地文件**：`knowledge/面试1.0.md` (43KB, 43585 bytes) — 可用的真实测试文档

## 二、当前版本功能清单

### 前端四个视图（单页面，侧边栏切换）

```
┌─ Header（顶栏）──────────────────────────┐
│  🧠 Private Agent v0.5                   │
│  [🧠 记忆 (N)] 徽章 ← 显示待审核数量      │
├─ Sidebar ───┬─ Main Workspace ───────────┤
│             │                            │
│ 💬 聊天     │  Chat View                 │
│ ✅ 审核 (N)  │  Review View              │
│ 📚 记忆库   │  Library View              │
│ 🔍 知识库   │  Knowledge View            │
│             │                            │
│ 会话列表     │                            │
│ + 新建会话   │                            │
└─────────────┴────────────────────────────┘
```

### 功能矩阵

| 功能模块 | 具体功能 | 需要测试 |
|---|---|---|
| **Chat 聊天** | SSE 流式输出、打字机效果、自动创建会话 | ✅ |
| **Conversation 会话** | 新建/切换/双击重命名/删除 | ✅ |
| **Memory Review 审核** | 查看待审核候选、accept/reject/edit+accept、批量全部接受/拒绝、按置信度筛选 | ✅ |
| **Memory Library 记忆库** | 搜索/分类筛选/来源筛选/删除单条/清空全部 | ✅ |
| **Knowledge Import 导入** | 选文件（系统原生弹窗多选 .md/.txt）、异步上传、每个文件独立进度条、完成变绿 | ✅ |
| **Knowledge Browse 浏览** | 双击文件 → 弹窗分页查看文本块(15条/页)、编辑/删除单块 | ✅ |
| **Knowledge Search 搜索** | 向量搜索 + 结果展示 | ✅ |
| **Knowledge Manage 管理** | 删除单文件、清空知识库 | ✅ |
| **Passive Memory 被动提取** | 聊天后 2 分钟自动提取候选、v0.5 自动分级(≥0.85 自动接受、<0.6 自动丢弃) | ✅ |
| **Memory Injection 记忆注入** | 聊天时自动将已确认记忆注入 LLM 上下文 | ✅ |

### 前端 JS 核心函数

```javascript
// 聊天
sendChat()              // SSE 流式请求
typewriterRender()       // 打字机效果
toggleTypewriter()       // 开关打字机

// 会话
newConversation()        // 新建
openConversation(id)     // 切换
renameConversation(id)   // 双击重命名
deleteConversation(id)   // 删除

// 记忆审核
loadCandidates()         // 加载待审核列表（10s 轮询）
acceptCandidate(id)      // 接受
rejectCandidate(id)      // 拒绝
acceptEdited(id)         // 编辑后接受
acceptAllCandidates()    // 批量接受
rejectAllCandidates()    // 批量拒绝
setReviewFilter()        // 按置信度筛选

// 记忆库
loadLibrary()            // 加载记忆列表
deleteMem(key)           // 删除一条
deleteAllMem()           // 清空

// 知识库
kbHandleFiles()          // 处理文件选择
kbStartImport()          // 开始异步导入
kbPollProgress()         // 每 0.8s 轮询进度
kbRefresh()              // 刷新已导入列表
kbOpenChunks(fname)      // 双击打开分页弹窗
kbLoadChunks()           // 加载分页数据
kbEditChunk(id)          // 编辑单块
kbSaveChunk(id)          // 保存编辑
kbDelChunk(id)           // 删除单块
kbDeleteFile(fname)      // 删除整个文件
kbClearAll()             // 清空知识库
kbSearch()               // 搜索
```

## 三、完整 API 列表

```
GET  /                          → 返回前端页面
GET  /health                    → 健康检查

POST /chat                      → 聊天（同步）
POST /chat/stream               → 聊天（SSE 流式）

POST /conversations             → 创建会话
GET  /conversations             → 列出会话
GET  /conversations/{id}        → 获取会话详情
POST /conversations/{id}/messages → 保存消息
PUT  /conversations/{id}/rename → 重命名
DELETE /conversations/{id}      → 删除会话

GET  /memory/candidates?status=pending → 列出候选
POST /memory/candidates/{id}/accept    → 接受（支持 body: {key,value,category}）
POST /memory/candidates/{id}/reject    → 拒绝
GET  /memory/list?category=     → 列出正式记忆
DELETE /memory/delete/{key}     → 删除一条记忆
DELETE /memory/delete-all       → 删除全部记忆
POST /memory/remember           → 手动保存记忆

POST /knowledge/search          → 搜索知识库
POST /knowledge/upload          → 上传文件（异步，返回 task_id）
GET  /knowledge/progress/{id}   → 查询导入进度
GET  /knowledge/stats           → 知识库统计
GET  /knowledge/chunks/{file}?page=&size= → 分页浏览
PUT  /knowledge/chunk/{id}      → 编辑单块
DELETE /knowledge/chunk/{id}    → 删除单块
DELETE /knowledge/chunks/{file} → 删除文件全部块
DELETE /knowledge/collection    → 清空知识库
POST /ingest/local              → 旧版目录导入（保留兼容）

GET  /messages/batch?ids=1,2,3  → 批量获取消息
```

## 四、可用测试资源

**真实文档**：
- `knowledge/面试1.0.md` — 43KB，中文 Markdown，约 152 个文本块
- `knowledge/uploads/` 目录 — 之前测试留下的各种文件

**创建测试文件的方法**：
- 前端点击按钮选择电脑上任意 .md/.txt 文件
- 或用 `echo "# test" > test.md` 在项目根目录创建

**测试记忆的方法**：
- 聊天时明确说"我叫XX"、"我喜欢用Python"等
- 等 2 分钟后被动提取会生成候选
- 或者用 POST /memory/remember 手动创建

## 五、用户问题

我需要一份**详细到每个点击步骤**的前端功能测试方案。我想在浏览器里打开 `http://localhost:8000`，按照一份清单逐项测试，验证 v0.5 所有功能是否正常。

**我的环境：**
- Windows 11，浏览器 Chrome/Edge
- Ollama 已运行，qwen2.5:7b + nomic-embed-text 可用
- 服务器已启动在 localhost:8000
- 有真实文档 `knowledge/面试1.0.md` (43KB)
- 我可以创建任意测试文件

**请给出：**

### A. 测试准备
- 需要提前准备哪些测试文件？
- 如何清空旧数据从零开始？

### B. 逐功能测试步骤（每个功能一个章节）
每个测试用例必须包含：
1. **操作步骤**：精确到点击哪个按钮、输入什么文字
2. **预期结果**：看到什么才算通过
3. **验证方法**：如何确认功能真的生效了

例如(不是实际格式)：
```
测试 1：新建会话
  操作：点击侧边栏 "+ 新建会话"
  预期：侧边栏出现 "新对话"，主区域聊天框清空
  通过：✅ 会话列表多了一项
```

### C. 需要覆盖的功能
1. **会话管理**：新建 / 切换 / 重命名 / 删除
2. **聊天 + 历史记忆**：SSE 流式、打字机、多轮对话记住上下文
3. **被动记忆提取**：聊天 → 等 2 分钟 → 查看审核列表
4. **记忆审核**：accept / reject / edit+accept / 批量操作 / 筛选
5. **记忆库**：搜索 / 筛选 / 删除
6. **记忆注入**：存一条记忆 → 新开会话 → 验证 LLM 引用了记忆
7. **知识库导入**：选择本地文件 / 查看进度 / 完成变绿
8. **知识库浏览**：双击文件 → 分页 / 编辑块 / 删除块
9. **知识库搜索**：搜索已有内容
10. **知识库管理**：删除文件 / 清空知识库

### D. 集成测试（跨模块）
- 完整闭环：聊天 → 生成候选 → 审核接受 → 新会话验证注入
- 知识库完整流程：导入 → 浏览 → 搜索 → 编辑 → 删除

### E. 边界情况
- 空状态（无会话、无记忆、无知识库）
- 错误处理（上传不支持的文件、编辑空内容）
- 大量数据（导入 43KB 文件）

### F. 验收检查表
- 给出一个可以直接打印的 checkbox 清单

**要求：**
- 操作步骤要足够具体，一个完全没看过这个项目的人照着做也能完成
- 不要写代码，写操作步骤
- 按依赖关系排序（先测基础功能，再测依赖功能）
- 每个功能标注预计耗时
