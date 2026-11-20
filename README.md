# StoryRole

> 从一本小说开始，进入里面的人。

StoryRole 现在的产品入口是**书架**：用户先选择或导入一本小说，进入小说页，再从这本书的角色开始对话。角色、场景、人设和对话都围绕一本具体的小说组织，而不是把所有内容塞进一个通用聊天列表。底层仍然是面向长篇叙事的时序人格运行系统。

<p align="center">
  <img src="docs/ui-shots-v4/shelf-1440.png" alt="StoryRole 书架" width="49%" />
  <img src="docs/ui-shots-v4/novel-1440.png" alt="StoryRole 小说与角色" width="49%" />
</p>

## 项目定位

普通角色聊天往往只有一句“你是某某角色”。模型很容易混合角色不同时期的经历，提前知道未来剧情，或者变成百科解说员。StoryRole 将角色视为一套随时间变化的人格运行时：

```text
小说原文 → 结构化切分与索引 → 角色解析 → 时期画像
                                             ↓
用户问题 → Laya 问题规划 → 证据 / 记忆 / 关系 / 联网信息
                                             ↓
                         快速或深度分析 → 角色化回答
                                             ↓
                              一致性审查与状态更新
```

核心目标不是让模型“知道更多剧情”，而是让它在有限证据和明确时期边界内，以一个具体人物的方式思考和回应。

## 核心能力

| 能力 | 实现方式 |
| --- | --- |
| 任意小说导入 | TXT、Markdown、多文件导入；解析章节、结构化切分、Embedding、Chroma 与 BM25 建索引 |
| 自定义角色 | 用户输入角色名，先从原文解析，再创建档案 |
| 自定义时期 | 用户定义时期，或由模型基于原文提出时期建议；每个时期独立生成画像 |
| 女娲式人格画像 | 提炼思维框架、表达方式、知识边界、关系、目标和反模式约束 |
| 混合检索 | 向量检索 + BM25 + 融合排序；需要时使用 DashScope Rerank |
| 双回答模式 | 快速模式偏重交互速度；深度模式增加受约束的分析计划与证据整理 |
| 正交联网模式 | Tavily 外部搜索可与快速/深度组合；外部资料不能改写角色人格 |
| 对话连续性 | 会话历史、动态关系与待确认的长期记忆候选 |
| 全链路观测 | `trace_id` 串起 Agent、阶段耗时、模型调用、Token、费用和降级信息 |

## 从小说到对话

### 1. 导入与索引

小说进入系统后，依次进行解析、章节识别、结构化切分和向量化；生成 Chroma 向量索引及持久化 BM25 索引。片段保留来源、章节和检索所需元数据。Embedding 后端可选本地 Ollama 或 DashScope，结果可通过数据库缓存复用。

### 2. 角色与时期

`character-resolver` 确认角色是否出现在原文中。用户可以直接定义人物时期，也可以调用 `character-period-analysis` 获取建议。`nuwa-profiler` 为每个时期分别生成并保存画像，避免早期和后期人格、关系与知识相互污染。

时期画像不仅是角色简介，还包含角色如何判断问题、如何表达、当前阶段知道什么，以及哪些未来事件不应出现在回答中。关系状态另存于 PostgreSQL，可随对话变化。

### 3. 一次聊天如何编排

```mermaid
flowchart LR
    U[用户问题] --> Q[query-planner / Laya]
    Q --> P{回答模式}
    P -->|快速| C[按需检索与整理]
    P -->|深度| D[分析计划与证据核对]
    D --> C
    W[Tavily 联网信息<br/>仅按需启用] --> C
    C --> R[角色认知与回答生成]
    R --> G[一致性审查]
    G --> M[记忆候选与关系更新]
```

Laya 先判断本轮需要哪些资源，例如小说证据、记忆、关系和时间线核查。深度模式在此基础上生成受约束的分析计划；它不是另一个独立 Agent，也不会向用户展示内部推理。回答由角色画像、当前时期和检索证据共同约束。

| 模式 | 主要取舍 | 适用问题 |
| --- | --- | --- |
| 快速 | 较少阶段与较短上下文，保持对话节奏 | 闲聊、情绪回应、简单追问 |
| 深度 | 更多证据、关系和动机分析 | 复杂事实、跨事件推断、关系冲突 |
| 联网开关 | 独立于快速/深度，按需加入外部资料 | 现实信息与扩展问题 |

## Agent 与系统架构

| Agent | 职责 |
| --- | --- |
| `character-resolver` | 根据原文解析并保存角色 |
| `character-period-analysis` | 提出时期范围建议 |
| `nuwa-profiler` | 生成并持久化时期画像 |
| `query-planner` | Laya 问题分类与资源规划，故障时可退回规则后端 |
| `deep-question-planner` | 深度问题的受约束分析与检索计划 |
| `context-curator` | 整理画像、小说证据、记忆、关系与联网结果 |
| `character-reasoning` / `role-cognition` | 形成角色立场、情绪和表达策略 |
| `relationship-state` / `memory-decision` | 更新动态关系与长期记忆候选 |
| `consistency-guard` | 检查人格、时期和证据边界 |
| `character-conversation` | 编排完整聊天流程 |

Agent 默认通过同进程 A2A 信封调用。`STORYROLE_A2A_TRANSPORT=http` 可将部分 Agent 改为 HTTP 服务，同时保留相同的调用协议。系统也提供 Agent Card 与 JSON-RPC 接口。

```mermaid
flowchart TB
    UI[StoryRole 前端] --> API[FastAPI]
    API --> ORCH[对话编排 / A2A]
    ORCH --> LAYA[Laya 决策]
    ORCH --> RAG[Chroma + BM25 + Rerank]
    ORCH --> LLM[OpenAI-compatible LLM]
    ORCH --> WEB[Tavily 可选搜索]
    ORCH --> DB[(PostgreSQL)]
    API --> REDIS[(Redis)]
    RAG --> EMB[Ollama / DashScope Embedding]
    API --> OBS[Trace 与模型观测]
    OBS --> DB
```

### 可观测性

每次导入、角色解析、画像生成和聊天都有独立 `trace_id`。流程记录包括 Agent 名称、阶段开始/结束时间、状态、错误、模型、供应商、Token、缓存命中、费用与耗时。聊天接口还返回当次 Trace 的摘要、步骤和模型调用；模型管理接口提供跨运行统计。

```json
{
  "trace_id": "...",
  "trace_summary": {},
  "trace_agents": [],
  "trace_steps": [],
  "trace_model_invocations": []
}
```

## 技术栈

| 层次 | 技术 |
| --- | --- |
| 后端 | Python 3.13+、FastAPI、Uvicorn |
| Agent | LangChain、A2A、Laya 决策后端、MCP 扩展接口 |
| 对话模型 | OpenAI-compatible API；当前统一为 deepseek-v4.1-flash-1017（阿里云 MaaS / DashScope 兼容端点） |
| 检索 | Chroma、BM25、Hybrid Fusion、DashScope Rerank |
| Embedding | Ollama 本地模型或 DashScope，支持缓存 |
| 存储 | PostgreSQL、Redis、JSONL 中间产物 |
| 前端 | HTML、CSS、JavaScript 静态页面 |
| 工具链 | uv、Docker Compose、pytest |

## 快速开始

### 1. 安装依赖与启动基础设施

```bash
uv sync
docker compose up -d postgres redis
```

默认将 PostgreSQL 映射到本机 `5433`、Redis 映射到 `6379`。

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，然后配置数据库连接、至少 32 字节的 `JWT_SECRET_KEY`、对话模型的 API Key 和 Base URL，以及 Embedding 后端。**不要把真实密钥提交到仓库。**

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DATABASE=three_body_agent
REDIS_HOST=localhost
REDIS_PORT=6379

JWT_SECRET_KEY=replace_with_a_random_string_at_least_32_bytes_long
DASHSCOPE_API_KEY=your_dashscope_api_key
OPENAI_API_KEY=your_dashscope_api_key
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
STORYROLE_CHAT_MODEL=deepseek-v4.1-flash-1017
STORYROLE_NUWA_MODEL=deepseek-v4.1-flash-1017
STORYROLE_REASONING_MODEL=deepseek-v4.1-flash-1017
STORYROLE_DECISION_BACKEND=laya

EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_EMBEDDING_MODEL=bge-m3
```

使用 Ollama 时需预先运行本地服务并拉取配置的模型。若使用 DashScope Embedding，将 `EMBEDDING_PROVIDER` 改为 `dashscope`；要走统一网关的 `qwen3.7-text-embedding`，改为 `openai`（换向量模型必须重建 Chroma 索引）。联网功能另需配置 `TAVILY_API_KEY`。模型名称和供应商能力以所用服务实际支持情况为准。

语言模型只使用 deepseek flash：项目里的 `STORYROLE_*_MODEL`、`ROLERAG_LLM_MODEL` 全部指向 `deepseek-v4.1-flash-1017`，不要混入其他模型 id（在 OpenAI 兼容的阿里云端点上，`deepseek-flash` 这个 id 会返回 404）。

同一把 key 在网关上还能调用 embedding、rerank、图片、语音等 182 个模型。用 `python scripts/list_models.py --roles` 查项目角色表，`python scripts/list_models.py --capability image` 查单类，接入方式见 `docs/model-gateway.md`；图片生成、图片理解、OCR、ASR、TTS、翻译的服务与 `/api/v1/media` 接口见 `docs/multimodal-api.md`。语言模型端点与回滚约束直接写在根目录 `.env` 的阿里云 / DeepSeek 配置段注释中。新前端在登录后从书架 `/` 进入，小说页地址形如 `/novels/三体-三部曲`，页面代码在 `frontend/app/`，页面脚本与设计系统在 `frontend/static/app/`；旧工作台和旧三体素材已归档到 `frontend/legacy/`，不再由主路由提供。

### 3. 初始化并启动

```bash
uv run python scripts/init_postgres.py
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
```

| 页面 | 地址 |
| --- | --- |
| 书架（产品入口） | http://127.0.0.1:8765/ |
| 新增小说 | http://127.0.0.1:8765/novels/new |
| 小说详情（示例） | http://127.0.0.1:8765/novels/三体-三部曲 |
| 对话收件箱 | http://127.0.0.1:8765/chats |
| 角色库 | http://127.0.0.1:8765/characters |
| 工具入口 | http://127.0.0.1:8765/tools |
| 用量 | http://127.0.0.1:8765/usage |
| 设置 | http://127.0.0.1:8765/settings |
| API 文档 | http://127.0.0.1:8765/docs |

`/novels` 与 `/library` 现在都落到书架；旧路径 `/storyrole`、`/agents`、`/periods`、`/chat`、`/models`、`/media/*`、`/multimodal` 仍保留 307 兼容跳转，但不再作为产品入口。

运行测试：

```bash
uv run pytest -q
```

## 常用接口

新前端统一走 `/api/app` 产品接口：登录、会话、角色、资料、工具和设置都按当前账号聚合成产品级返回，具体契约以 `app/api/web.py` 与运行中的 `/docs` 为准。底层角色对话仍由下面的 `/api/v1/storyrole` 接口执行。

```text
GET  /api/app/summary
GET  /api/app/conversations
POST /api/app/characters/{character_id}/messages
GET  /api/app/usage?days=30
GET  /api/app/tools/models
PUT  /api/app/settings

POST /api/v1/novels/imports
GET  /api/v1/novels/imports/{import_id}
POST /api/v1/storyrole/novels/{novel_id}/characters/resolve
POST /api/v1/storyrole/novels/{novel_id}/characters/setup
POST /api/v1/storyrole/novels/{novel_id}/characters/{character_id}/period-analysis
POST /api/v1/storyrole/novels/{novel_id}/characters/{character_id}/periods/{period_id}/profile
POST /api/v1/storyrole/novels/{novel_id}/characters/{character_id}/chat
POST /api/v1/storyrole/novels/{novel_id}/characters/{character_id}/chat/stream
GET  /api/v1/models/usage
GET  /api/v1/models/dashboard
GET  /api/v1/models/traces/{trace_id}
GET  /api/v1/a2a/cards
```

聊天请求的 `mode` 支持 `quick`、`deep`、`auto`；`web_mode` 支持 `off`、`on`。具体请求结构与认证方式以运行中的 `/docs` 为准。

## 目录结构

```text
app/
  agents/a2a/            # A2A 信封、注册与传输
  agents/decision/       # Laya 与规则决策后端
  agents/storyrole/      # StoryRole Agent
  api/v1/                # 业务与监控 API
  observability/         # Trace、模型调用与证据图
  rag/                   # 解析、切分、索引、检索和重排
  services/              # 小说导入与聊天服务
  storage/               # PostgreSQL、Redis 与仓储层
frontend/app/             # 15 个新页面；static/app/ 是页面脚本与设计系统；legacy/ 是旧单页归档
configs/eval/            # 可重复评测配置
data/                    # 原始数据、处理中间产物与本地索引
docs/                    # 架构说明与展示截图
scripts/                 # 初始化、索引、评测脚本
tests/                   # 单元与流程测试
```

## 工程边界与演进

- 时序边界依靠画像、检索过滤和生成约束共同实现；仍需持续增加章节/事件级回归案例。
- 外部联网资料仅作补充证据，不会自动更新小说设定或角色画像。
- 长期记忆采用候选确认流程，避免一次对话将偶然表达永久固化。
- 检索质量、人格一致性、延迟和成本需要通过固定评测集持续验证，不能仅凭演示对话判断。

> StoryRole 希望回答的不是“这个人物的资料是什么”，而是“处在这个时间点的他会如何看待这件事”。
