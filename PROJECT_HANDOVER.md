# 项目交接文档

> 生成日期：2026-07-14  
> 当前分支：`backend`  
> 最近提交：`0de5dbb complete auth and ai integration improvements`  
> 说明：本文描述的是**当前工作区状态**。工作区存在尚未提交的后端改动、测试、脚本和文档；其中新闻接口等功能已经在本地实现并通过测试，但尚未全部进入 Git 提交。

# 项目基本信息

## 项目名称

网络舆情事件智能分析系统（`network-public-opinion-system`）。

## 技术栈

- Web 框架：FastAPI 0.115
- ASGI 服务：Uvicorn 0.30
- ORM：SQLAlchemy 2.0
- 数据校验：Pydantic 2.9、pydantic-settings
- 数据库：MySQL，驱动为 PyMySQL
- 外部 HTTP 调用：Requests
- 测试：Python `unittest`、FastAPI TestClient、内存 SQLite

## 代码位置

- 仓库根目录：`E:\network-public-opinion-system`
- 后端目录：`backend`
- 后端应用：`backend/backend_app`
- 启动入口：`backend/backend_app/main.py`
- 测试目录：`backend/tests`
- 数据脚本：`backend/scripts`

## 数据库信息

- 数据库类型：MySQL
- 数据库名称：`public_opinion`
- 连接配置来自 `backend/.env`，配置项包括数据库主机、端口、用户名、密码和库名。
- 本文不记录数据库地址、账号或密码。
- `backend/database.sql` 当前只显式创建 `public_opinion` 数据库和 `users` 表；`events`、`articles`、`analysis`、`ai_results` 主要依赖 SQLAlchemy ORM 的 `Base.metadata.create_all()` 创建。
- 当前没有数据库版本迁移工具。`create_all()` 只能创建缺失表，不能升级已有表结构。

## 服务端口

- README 中使用 `uvicorn backend_app.main:app --reload` 启动，未指定端口时默认监听 `8000`。
- MySQL 端口和 5 号 AI 服务地址均由环境配置提供，本文不记录实际地址。

## 启动方式

```powershell
cd backend
pip install -r requirements.txt
uvicorn backend_app.main:app --reload
```

Swagger 默认入口为 `/docs`，OpenAPI JSON 为 `/openapi.json`。

# 系统整体架构

```text
爬虫（3号）
  ↓ POST /internal/articles
articles
  ↓ 待分析数据 /internal/articles/pending
NLP分析（4号）
  ↓ POST /internal/analysis
analysis
  ↓ AggregationService
事件聚合
  ↓ 绑定 articles.event_id 与 analysis.event_id
events
  ↓ AIService.build_context(event_id)
AI模块（5号服务）
  ↓ AIProvider HTTP 调用，结果可保存至 ai_results
FastAPI 对外接口
  ↓
前端（2号）
```

核心模块职责：

- `internal/articles.py`：接收爬虫新闻，提供待分析新闻。
- `internal/analysis.py`：接收 NLP 结果，触发事件聚合，并按条件尝试生成 AI 报告。
- `services/aggregation_service.py`：根据 `similar_news` 查找已有事件，或创建新事件，再绑定新闻和分析记录。
- `routers/events.py`：事件列表、事件详情。
- `routers/news.py`：首页新闻列表、指定事件新闻列表。
- `services/ai_service.py`：构建 EventContext，执行问答、报告和核验业务。
- `services/ai_provider.py`：封装对 5 号 AI 服务的 HTTP 调用。

# 项目目录结构

```text
network-public-opinion-system/
├── backend/
│   ├── backend_app/
│   │   ├── core/       # 密码安全等基础能力
│   │   ├── internal/   # 爬虫、NLP、AI输入内部接口
│   │   ├── models/     # SQLAlchemy ORM
│   │   ├── routers/    # 对外 API
│   │   ├── schemas/    # Pydantic 请求/响应模型
│   │   ├── services/   # 聚合、事件、统计、AI 服务
│   │   ├── utils/      # 统一响应工具
│   │   ├── config.py
│   │   ├── database.py
│   │   └── main.py
│   ├── scripts/        # 测试数据和端到端数据脚本
│   ├── tests/          # unittest 测试
│   ├── database.sql
│   ├── requirements.txt
│   └── README.md
├── docs/               # 接口联调和前端展示说明（当前未跟踪）
├── PROJECT_HANDOVER.md
└── README.md
```

# 数据库设计

当前 ORM 没有声明 `ForeignKey` 或 `relationship`，表之间通过普通 ID 字段在业务代码中关联。数据库层不会自动保证这些关联的引用完整性。

## events

事件主表。

关键字段：

| 字段 | 含义 |
| --- | --- |
| `event_id` | 事件主键 |
| `title` | 事件标题 |
| `summary` | 事件摘要 |
| `heat` | 聚合后的事件热度 |
| `risk_level` | 风险等级 |
| `stage` | 生命周期阶段 |
| `create_time` | 创建时间 |
| `update_time` | 更新时间 |
| `status` | 事件状态 |
| `extra` | 扩展 JSON |

## articles

新闻主表，系统中 news 对应 ORM 模型 `Article` 和数据库表 `articles`。

关键字段：

| 字段 | 含义 |
| --- | --- |
| `news_id` | 新闻主键 |
| `event_id` | 所属事件 ID，可为空 |
| `title`、`content` | 标题和正文 |
| `source`、`url` | 来源和原文地址 |
| `publish_time`、`crawl_time` | 发布时间和采集时间 |
| `platform` | 平台 |
| `author` | 作者 |
| `account_id`、`account_name`、`account_type` | 发布账号信息 |
| `is_official` | 是否官方账号 |
| `repost_count`、`comment_count`、`like_count` | 互动指标 |
| `reference_urls`、`quoted_news_ids` | 引用信息 |
| `parent_news_id`、`duplicate_group_id` | 传播和去重辅助字段 |

## analysis

每篇新闻的 NLP 分析结果。

关键字段：

| 字段 | 含义 |
| --- | --- |
| `id` | 分析记录主键 |
| `news_id` | 对应 `articles.news_id` |
| `event_id` | 对应 `events.event_id` |
| `summary`、`processed_text` | NLP 摘要和处理后正文 |
| `keywords` | 关键词 JSON |
| `positive`、`neutral`、`negative` | 情感比例 |
| `heat_score` | 单篇分析热度 |
| `stage`、`risk_level` | 阶段和风险等级 |
| `similar_news` | 相似新闻 ID 列表 |
| `missing_fields` | 缺失字段列表 |

## ai_results

按事件保存 AI 派生结果。

关键字段：

| 字段 | 含义 |
| --- | --- |
| `id` | 主键 |
| `event_id` | 对应 `events.event_id` |
| `overview` | 事件概览 JSON |
| `ai_report` | AI 报告 JSON |
| `authenticity` | 真实性核验 JSON |
| `propagation_analysis` | 传播分析 JSON |
| `propagation_path` | 传播路径 JSON |
| `generated_at` | 生成时间 |
| `provider` | AI Provider 标识 |
| `status`、`error_message` | 执行状态和错误信息 |

## users

用户表。

关键字段：

| 字段 | 含义 |
| --- | --- |
| `id` | 用户主键 |
| `username` | 唯一用户名，非空 |
| `nickname` | 昵称，非空 |
| `password` | 密码哈希，长度 255，非空 |
| `preferences` | 用户偏好 JSON |

## 主要关系

```text
events.event_id
  ├── articles.event_id
  ├── analysis.event_id
  └── ai_results.event_id

articles.news_id
  └── analysis.news_id
```

# 已完成功能

## 1. 用户注册登录

### 注册

```http
POST /api/register
Content-Type: application/json
```

```json
{
  "username": "test001",
  "password": "123456",
  "nickname": "测试用户"
}
```

- 用户名长度：3～50。
- 密码长度：6～128。
- 昵称长度：1～50。
- 重复用户名返回 HTTP 409。
- 密码使用 PBKDF2-SHA256、随机盐和 600000 次迭代存储，不保存明文。

### 登录

```http
POST /api/login
Content-Type: application/json
```

```json
{
  "username": "test001",
  "password": "123456"
}
```

- 用户不存在或密码错误返回 HTTP 401。
- 登录成功返回 `user_id`、`username`、`nickname`。
- **JWT：未实现。**
- **Session/Cookie 登录态：未实现。**

## 2. 事件接口

### `GET /api/events`

返回轻量事件列表，可通过 `sort=time` 或 `sort=heat` 排序。现有字段：

- `event_id`
- `title`
- `summary`
- `heat`
- `risk_level`
- `stage`
- `create_time`

该接口不返回大量新闻正文，适合首页右侧事件热榜。

### `GET /api/events/{event_id}`

返回事件详情，包括：

- 事件基本信息
- `overview.article_count`
- 新闻时间线
- 报道数量趋势、趋势标签和高亮点
- 关键词汇总
- 平均情感比例
- 平台分布
- 最新 AI 报告、真实性结果、传播分析和传播路径

事件不存在时返回 HTTP 404。

## 3. 新闻接口

### `GET /api/news`

用于首页左侧热点新闻速览。以 `articles` 为主表，通过：

```text
articles.news_id = analysis.news_id
```

左关联分析结果。无 analysis 的新闻仍会返回。

返回字段：

- `news_id`
- `event_id`
- `title`
- `source`
- `publish_time`
- `summary`
- `content`
- `url`
- `heat`（来自 `analysis.heat_score`）
- `risk_level`（来自 `analysis.risk_level`）
- `stage`（来自 `analysis.stage`）
- `platform`

摘要优先使用 `analysis.summary`；缺失时使用正文前 200 字符。

### `GET /api/events/{event_id}/news`

返回指定事件下的全部新闻，按发布时间倒序排列。

返回字段：

- `news_id`
- `event_id`
- `title`
- `source`
- `publish_time`
- `summary`（正文前 200 字符）
- `content`
- `url`

事件不存在时返回 HTTP 404。

> 当前状态：`routers/news.py`、`schemas/news.py` 及相关测试位于工作区，但尚未提交到 Git。

## 4. AI 报告

```http
POST /api/ai/report/{event_id}
```

调用链：

```text
AI Router
  → AIService.generate_report(event_id)
  → AIService.build_context(event_id)
  → RealAIProvider.report(context)
  → 外部 5 号 AI 服务
  → ai_results.ai_report
```

报告成功后，`ai_results.status` 为 `success`，报告可通过以下接口读取：

```http
GET /api/ai/report/{event_id}
GET /api/events/{event_id}
```

外部服务地址来自 `AI_SERVER_URL` 环境配置。

## 5. AI 问答

```http
POST /api/ai/ask
Content-Type: application/json
```

当前请求格式：

```json
{
  "event_id": 25,
  "question": "请分析该事件的舆情发展过程和当前主要风险"
}
```

- `event_id` 必须大于 0。
- `question` 长度为 1～2000。
- 后端根据 `event_id` 查询事件、文章和分析数据，构造：

```json
{
  "event": {},
  "question": ""
}
```

再由 `AIProvider` 发送给 5 号 AI 服务。
- 当前为单轮问答，不保存会话历史。

# 测试数据

## seed_test_event.py

路径：`backend/scripts/seed_test_event.py`。

用途：生成一套完整的联调事件数据，模拟“爬虫完成 + NLP 完成 + 事件聚合完成”的状态。

生成内容：

- 1 个 event
- 5 篇 articles
- 5 条 analysis
- 5 个不同来源、平台和发布时间
- 每篇正文不少于 1000 字符
- 热度按时间从低到高变化

脚本特性：

- 使用当前 ORM。
- 插入前检查固定 seed 标识和文章 URL。
- 缺失才插入，不覆盖已有记录。
- 可重复执行；第二次执行新增数量应为 0。
- 自动验证事件数、文章数、分析数、正文长度和热度分布。

当前本地示例数据的 `event_id` 为 `25`。该 ID 由数据库自增生成，仅代表当前本地数据库；在其他环境运行时可能不同。

运行：

```powershell
cd backend
python scripts/seed_test_event.py
```

# 当前测试状态

测试命令：

```powershell
cd backend
python -m unittest discover -s tests -v
```

2026-07-14 实际执行结果：

```text
Ran 19 tests in 1.434s
OK
```

覆盖范围：

- AI Ask 请求模型、OpenAPI 契约和 Service 调用
- 注册、重复用户名、登录、错误密码、未知用户
- 事件列表保持轻量
- 首页新闻列表和事件新闻列表
- 新闻摘要回退逻辑
- 新闻接口 Swagger Schema
- 事件趋势的小时/天粒度及高亮点

非阻塞警告：

- SQLAlchemy 提示 `datetime.utcnow()` 将弃用，后续应改为时区感知时间。
- 测试结束出现 SQLite 连接资源警告，当前不影响 19 项测试通过，但应补齐测试连接清理。

# 前端联调说明

当前仓库中没有实际前端工程代码；以下为后端接口与既定首页布局的对应关系。

## 首页

```text
左侧：新闻列表
  → GET /api/news

右侧：事件热榜
  → GET /api/events?sort=heat
```

交互建议：

1. 点击新闻时保留 `news_id`，用于新闻定位、真实性核验和后续证据关系。
2. 新闻带有 `event_id` 时，可跳转至 `/api/events/{event_id}` 对应的事件详情页。
3. 点击事件热榜项时使用 `event_id` 获取：
   - `GET /api/events/{event_id}`：事件分析详情；
   - `GET /api/events/{event_id}/news`：该事件全部新闻；
   - `POST /api/ai/report/{event_id}`：生成报告；
   - `POST /api/ai/ask`：事件上下文问答。
4. `news_id` 是新闻主键，`event_id` 是事件主键，两者不能混用。
5. 新闻可能尚未聚合到事件，此时 `event_id` 可以为空；前端应提供无事件归属状态。
6. 新闻没有 analysis 时，`heat`、`risk_level`、`stage` 可能为空。

# 当前未完成事项

## AI 问答进一步优化

- 当前只支持单轮问答。
- 问答历史、引用证据、置信度和会话持久化均未实现。
- Provider 失败的统一 HTTP 错误语义仍需完善。

## 5 号 AI 服务网络问题

- AI 报告和开放式问答依赖外部 `AI_SERVER_URL`。
- 网络、部署、超时或外部服务不可用会导致 AI 功能失败；该问题不能仅由当前仓库保证。
- 应在目标部署环境持续验证 5 号服务健康检查、超时和有限重试策略。

## previous_heat_score 生命周期

- **未实现。**
- 模型、Schema、路由和 AI 上下文中均没有 `previous_heat_score`。
- 当前只有单篇 `analysis.heat_score` 和聚合后的 `events.heat`，没有历史热度生命周期存储机制。

## 证据图谱

- **未实现。**
- 文档中存在证据图谱接口与页面说明，但当前 `AIProvider`、`AIService` 和 FastAPI 路由没有 evidence-graph 方法或公开接口。
- 当前数据库也没有证据图谱专用缓存表或字段。

## 前端最终联调

- 当前仓库没有前端源码，尚未完成真实页面联调、路由跳转、错误态和空态验收。

## 内部 AI 输入接口不一致

- `/internal/analysis/pending` 当前引用 `Analysis.ai_generated`。
- `Analysis` ORM 模型中没有 `ai_generated` 字段。
- 该接口当前属于未完成状态，调用时存在运行时错误风险。

## 用户偏好接口

- `/api/user/preferences` 当前直接选择数据库中的第一个用户，没有用户身份认证。
- 无用户时的临时用户创建逻辑没有提供非空 `nickname`，并使用非哈希占位密码，与当前 User 模型和认证实现不一致。
- 不应将该接口视为正式的用户级偏好功能。

## 数据库迁移

- 未接入 Alembic 或其他迁移工具。
- `database.sql` 只覆盖 `users`，不能完整重建全部业务表。
- ORM 改动不会自动升级已有 MySQL 表。

## 登录态和权限

- JWT、Session、权限校验和受保护接口均未实现。

# 下一步开发建议

按优先级建议如下：

1. **P0：整理并提交当前工作区。** 按功能拆分新闻接口、事件趋势、聚合改动、测试和种子脚本；排除 `.env`、缓存、日志、IDE 文件和含环境地址的临时文件。
2. **P0：引入数据库迁移机制。** 使用 Alembic 建立当前五张主表的基线迁移，停止依赖 `create_all()` 升级结构。
3. **P0：修复内部接口模型不一致。** 明确是否需要 `analysis.ai_generated`；若需要，应设计字段和迁移，否则移除 `/internal/analysis/pending` 的错误条件。
4. **P1：完成前端首页与事件详情联调。** 接入 `/api/news`、`/api/events`、`/api/events/{event_id}` 和 `/api/events/{event_id}/news`，验证加载态、空态和错误态。
5. **P1：完善 AI 服务可靠性。** 增加健康检查、统一错误码、超时策略、有限重试和敏感错误屏蔽。
6. **P1：确定认证范围。** 若系统需要真实登录态，增加 JWT 或 Session，并让用户偏好绑定当前认证用户。
7. **P2：设计热度历史。** 明确 `previous_heat_score` 的来源、更新时机、历史表结构和 EventContext 传递方式。
8. **P2：实现证据图谱。** 先增加后端代理接口和响应 Schema，再实现前端 ECharts 页面；MVP 可实时生成，稳定后再考虑缓存。
9. **P2：扩充测试和清理警告。** 增加 MySQL 集成测试、AI 服务故障测试、事件聚合测试，并解决时间 API 弃用和 SQLite 连接资源警告。

# Git 工作区注意事项

生成本文时工作区并非 clean。除本交接文档外，当前还有既有的已修改/未跟踪内容，包括：

- 分析接收、文章接收、事件聚合、趋势统计等后端改动；
- 新闻路由、新闻 Schema 和相关测试；
- 测试数据脚本；
- `.env`、缓存、日志、IDE 文件及联调文档。

提交前必须使用精确文件路径暂存，不要执行无筛选的 `git add .`。
