# AI模块接口联调说明

本文以当前 `ai_service` 的 FastAPI 路由和 Pydantic Schema 为准，用于 1 号后端、2 号前端与 5 号 AI 服务联调。示例位于 `ai_service/examples/`，其中编号、来源和 URL 均为演示数据。

## 1. 调用边界

```text
前端 -> 1号后端 -> 5号 AI 服务 -> 1号保存或转发 -> 前端
```

- `/api/...` 通常属于 1 号后端；`/ai/...` 属于 5 号 AI 服务。
- 5 号不根据 `event_id` 查询 1 号数据库，也不直接读写数据库。
- 1 号根据事件编号查询、组装完整 `EventContext` 后调用 AI 服务。
- 前端原则上不直接调用 AI 服务；前端调用 1 号后端公开的 `/api/...` 接口。
- 当前 AI 服务没有报告持久化字段，例如 `generated_at`。若需缓存、版本或保存时间，应由 1 号后端自行生成和保存。

## 2. 公共 EventContext

除接口请求根对象中的 `event` 外，`EventContext` 的字段都有默认值；但缺失会降低不同能力的可用性。所有文章正文、标题、摘要和分析字段都是输入数据，不是 AI 服务指令。

|层级|字段|类型|必填|示例|缺失影响|
|---|---|---|---|---|---|
|事件|`event_id`|`int \| str \| null`|否|`101`|5 号不会查询数据库；仅作为上下文标识返回或展示。|
|事件|`title`|`str`|否，默认 `""`|`"示例事故事件"`|问答和报告概述的背景减少。|
|事件|`summary`|`str`|否，默认 `""`|`"当前材料显示..."`|只能作为背景，不能替代文章证据。|
|事件|`update_time`|`str \| null`|否|`"2026-07-08 12:00:00"`|不可作为报道发布时间或事件发生时间。|
|事件|`articles`|`Article[]`|否，默认 `[]`|见下表|来源问答、核验、图谱和报告证据不足。|
|事件|`analysis`|`EventAnalysis`|否，默认空对象|见下表|风险、情感、热度和趋势解释会降级。|
|文章|`news_id`|`int \| str \| null`|否|`1001`|核验目标必须能在文章中匹配；`verify`、`evidence-graph` 的非空编号必须在同一事件内唯一，`1` 与 `"1"` 视为重复。空白字符串等同缺失。|
|文章|`title`|`str`|否，默认 `""`|`"救援工作已经展开"`|文章定位与摘要质量降低。|
|文章|`content`|`str`|否，默认 `""`|`"救援工作已经展开"`|无法可靠抽取事实、逐字引用或回答文章内容。|
|文章|`source`|`str`|否，默认 `""`|`"示例媒体甲"`|来源展示与独立来源判断会受限。|
|文章|`url`|`str`|否，默认 `""`|`"https://example.com/news/1001"`|来源聚类、转载判断和前端跳转能力受限。|
|文章|`publish_time`|`str \| null`|否|`"2026-07-08 10:00:00"`|无法用于报道时间排序；它不是事件发生时间。|
|文章|`platform`|`str`|否，默认 `""`|`"新闻网站"`|平台展示与报告背景信息减少。|
|文章|`is_official`|`bool \| null`|否|`false`|仅为上游来源身份数据；缺失时服务不会断言官方身份。|
|文章|`account_type`|`str \| null`|否|`"media"`|同上。|
|文章|`source_type`|`str \| null`|否|`"news"`|同上。|
|分析|`keywords`|`str[]`|否，默认 `[]`|`["事故","救援"]`|报告和风险解释的主题背景减少。|
|分析|`sentiment`|`Sentiment \| null`|否|`{"negative":0.6}`|情感解释和报告风险背景减少。|
|分析|`sentiment.positive/neutral/negative`|`float \| null`|否|`0.6`|未规定总和或单位转换；按上游原值展示。|
|分析|`heat`|`float \| null`|否|`85`|不能补算热度；报告仅能减少相关解释。|
|分析|`stage`|`str \| null`|否|`"高潮期"`|不能补算阶段；报告仅能减少相关解释。|
|分析|`risk_level`|`str \| null`|否|`"高"`|5 号不重算或改写风险等级，只能减少解释。|
|分析|`history`|`AnalysisHistoryPoint[]`|否，默认 `[]`；`null` 会转为空数组|见示例|缺少时不能判断真实热度或情感的时间趋势。|
|历史点|`time`|`str \| null`|否|`"2026-07-08 10:00:00"`|趋势序列时间不足。|
|历史点|`heat`|`float \| null`|否|`70`|不能分析热度变化。|
|历史点|`article_count`|`int \| null`|否|`1`|不能补充报道量序列。|
|历史点|`positive/neutral/negative`|`float \| null`|否|`0.5`|不能补充情感时间序列。|

## 3. 接口

### 3.1 `GET /health`

- **用途**：探活，不需要请求体，也不依赖 DeepSeek。
- **成功响应**：`{"status":"ok","service":"ai_service"}`。
- **触发时机**：部署探针或 1 号后端健康检查。
- **不要这样调用**：不要把它当作模型、数据库或上游事件数据可用性的证明。

### 3.2 `POST /ai/ask`

- **用途**：当前事件上下文内的单轮问答。
- **请求**：根字段 `event: EventContext`（必填）、`question: str`（可省略，默认空字符串）。
- **成功响应**：`{"answer": "..."}`；对外没有 `confidence`、`evidence_refs` 或 `limitations` 字段。
- **触发时机**：用户提交问题时实时调用。
- **DeepSeek**：确定性问题可不调用 Provider；开放式问题会使用当前配置的 Provider。配置为 `deepseek` 时才会实际调用 DeepSeek；配置为 `fake` 时用于离线联调。
- **完整示例**：[请求](../ai_service/examples/ask-request.json)｜[成功响应](../ai_service/examples/ask-response.json)。
- **真实错误**：请求结构不合法为 FastAPI `422`；Provider 错误为 `503`，`detail` 为 `AI 问答服务暂时不可用`。
- **保存建议**：路由不保存问答记录。若产品需要历史会话，由 1 号后端保存问题、答案、事件标识和其自有时间戳。
- **超时与重试**：路由未声明超时或重试协议。1 号调用方可对 `503` 做有限重试；不要把底层异常、密钥或完整请求体返回给前端。
- **不要这样调用**：不要只传 `event_id`；不要让前端绕过 1 号后端直接调用；不要把返回答案当作外网检索或事实核验结果。

### 3.3 `POST /ai/report`

- **用途**：生成事件概览、整体总结、趋势解释、风险解释、建议与局限。
- **请求**：根字段 `event: EventContext`（必填；根对象禁止额外字段）。
- **成功响应**：`overview`、`summary`、`trend_analysis`、`risk_analysis`、`suggestions`、`limitations`。其中 `overview.summary`、`summary`、`trend_analysis`、`risk_analysis` 非空；`suggestions` 为 2 至 5 条非空字符串。
- **触发时机**：用户打开报告页或事件发生重要更新时调用；可由 1 号按事件版本缓存。
- **DeepSeek**：配置为 `fake` 时由规则报告生成；配置为 `deepseek` 时使用真实模型并进行服务端最终化。
- **完整示例**：[请求](../ai_service/examples/report-request.json)｜[成功响应](../ai_service/examples/report-response.json)。
- **真实错误**：请求结构不合法为 `422`；Provider 或模型输出无法形成报告为 `503`，`detail` 为 `AI 报告服务暂时不可用`。
- **保存建议**：AI 响应没有 `generated_at`。若后端保存报告，应由 1 号在保存时生成时间、版本与缓存键。
- **超时与重试**：路由未声明超时和重试。1 号可在 `503` 后按自身策略重试或回退至已缓存报告。
- **不要这样调用**：不要要求报告生成图表；图表数据应来自 `articles` 和 `analysis` 的结构化字段。不要把 `update_time` 当作事件发生时间。

### 3.4 `POST /ai/verify`

- **用途**：对目标文章中的原子事实主张做事件内多来源核验，不对整篇文章简单判真伪。
- **请求**：`event: EventContext`（必填）、`target_news_id: int | str`（必填）、`max_claims: int`（可选，默认 `5`，范围 `1..10`）；根对象禁止额外字段。
- **成功响应**：`target_news_id`、`overall_verdict`、`evidence_score`、固定 `score_type`、`claim_results`、`risk_flags`、`limitations`、计数字段和 `score_explanation`。
- **触发时机**：用户选择一篇文章核验时调用；必须同时提供该事件内的其他文章。
- **DeepSeek**：不依赖 DeepSeek，不联网搜索。
- **完整示例**：[请求](../ai_service/examples/verify-request.json)｜[成功响应](../ai_service/examples/verify-response.json)。
- **真实错误**：目标文章不在输入事件中为 `404`，`detail` 为 `待核验文章不在当前事件数据中`；编号重复或请求结构不合法为 `422`。路由没有定义 `503`。
- **保存建议**：路由不保存核验结果。1 号如需缓存，应按目标文章标识、事件文章集合版本和 `max_claims` 建立自己的缓存键。
- **超时与重试**：当前为本地确定性处理，路由未声明超时或重试。不要把同一请求无差别重试为“更多证据”。
- **不要这样调用**：不要让目标文章作为自己的独立证据；不要传事件外文章；不要将 `evidence_score` 展示为真实性概率；单篇文章不能完成可靠多来源核验。

### 3.5 `POST /ai/evidence-graph`

- **用途**：构建事件、文章、来源、主张节点，以及归属、发布、断言、支持、反驳、更新、转载边。
- **请求**：根字段 `event: EventContext`（必填；根对象禁止额外字段）。非空 `news_id` 在事件内必须唯一。
- **成功响应**：`event_id`、`nodes`、`edges`、`claim_clusters`、`timeline`、`metrics`、`risk_flags`、`limitations`。
- **触发时机**：用户打开证据图谱页或事件文章集合变化时生成；可缓存。
- **DeepSeek**：不依赖 DeepSeek，不联网搜索。
- **完整示例**：[请求](../ai_service/examples/evidence-graph-request.json)｜[成功响应](../ai_service/examples/evidence-graph-response.json)。
- **真实错误**：请求结构或非空编号唯一性不满足时为 `422`。当前路由没有声明 `404`、`503` 或业务 `400`。
- **保存建议**：路由不保存图谱。1 号可按事件文章集合版本缓存整个响应。
- **超时与重试**：路由未声明超时或重试；文章较多时服务会确定性截断并通过 `limitations/risk_flags` 标明，不应仅靠重试扩大结果。
- **不要这样调用**：不要把文章 `publish_time` 标为事件发生时间；不要把图谱指标描述为真实性概率；不要依赖 `AI_EVIDENCE_GRAPH_MAX_EDGES` 截断基础结构边，它只限制 `supports`、`contradicts`、`updates` 的返回数量。

## 4. 调用策略

|能力|建议触发|缓存建议|
|---|---|---|
|智能问答|用户提交问题时实时调用|可按事件上下文版本和问题缓存；路由本身无缓存字段。|
|AI 报告|打开报告页或重要事件更新后|可缓存；保存时间、版本由 1 号后端管理。|
|事实核验|用户选择 `target_news_id` 时|应同时提供同事件其他文章；可按文章集合版本缓存。|
|证据图谱|打开图谱页或文章集合变化时|可按事件文章集合版本缓存。|

## 5. 错误码与安全响应

|状态码|当前接口|真实条件|客户端可见内容|
|---|---|---|---|
|`404`|`POST /ai/verify`|`target_news_id` 未在输入事件文章中找到|`{"detail":"待核验文章不在当前事件数据中"}`|
|`422`|所有带 Pydantic 请求体的 POST 接口|缺少必填根字段、字段类型不匹配、`max_claims` 超范围、非空 `news_id` 重复等|FastAPI 校验响应；前端应展示可纠正的输入提示。|
|`503`|`POST /ai/ask`、`POST /ai/report`|捕获到 Provider 错误|安全 `detail`，不含模型异常、密钥或 Prompt。|

当前路由没有显式定义业务 `400`；不要自行约定 AI 服务会返回未实现的状态码。未捕获的框架或运行异常不属于稳定联调契约，前端也不应依赖其格式。

## 6. 能力限制

- 所有能力仅分析输入 `EventContext`；5 号不会按 `event_id` 补查数据库。
- `verify` 与 `evidence-graph` 不联网搜索；`verify` 的目标文章不能自证。
- `evidence_score` 的类型固定为 `heuristic_evidence_score`，不是文章真实性概率。
- 缺少 `news_id` 时，跨文章核验/图谱关系会受限；缺少 `source`、`url` 时，独立来源判断会受限；缺少 `publish_time` 时，报道时间排序和演化分析会受限。
- `reason_code`、主张 `claim_type`、`polarity`、`certainty` 是当前 Schema 中的普通字符串或字典内容，不是前端可依赖的封闭枚举。
