# AI模块前端展示说明

前端原则上调用 1 号后端的 `/api/...`，由后端转发或返回 5 号 AI 服务的 `/ai/...` 结果。本说明只映射当前真实响应字段；不存在于响应中的字段不得假定可用。

## 1. 智能问答页面

- **输入区**：聊天输入框提交问题。后端需提供当前事件上下文，不应只转发 `event_id`。
- **回答区**：使用 `/ai/ask` 的 `answer: string` 渲染 AI 回答气泡。
- **依据材料**：`/ai/ask` 对外响应只有 `answer`，没有 `evidence_refs` 或引用列表。若产品需展示“依据材料”，应由 1 号后端从其已组装的 `EventContext.articles` 另行提供新闻标题、来源、URL 和发布时间；不要从答案文本反向解析或虚构引用。
- **加载/失败**：请求中显示加载态；`503` 显示“AI 问答服务暂时不可用”，`422` 显示请求或上下文校验失败。不要把内部异常展示给用户。

## 2. AI 报告页面

`/ai/report` 响应字段与推荐展示位置：

|字段|展示方式|
|---|---|
|`overview.time/location/cause/persons/summary`|事件概览。`null` 或空数组应显示“当前材料未明确”，不要用空白占位。|
|`summary`|核心进展/整体总结正文。|
|`trend_analysis`|趋势分析文本；它可能说明时间序列不足，不应强行渲染升降图。|
|`risk_analysis`|风险分析正文；它解释上游结果，不是重新计算的风险等级。|
|`suggestions`|2 至 5 条建议列表。|
|`limitations`|局限与数据不足列表；为空时可隐藏本区。|

报告接口不返回 `generated_at`。若页面需要生成时间，必须由 1 号后端在保存或缓存报告时提供。

## 3. 事实核验页面

### 3.1 总览卡片

|字段|展示规则|
|---|---|
|`overall_verdict`|使用下方中文映射显示。|
|`evidence_score`|显示为“启发式证据强度：N/100”，不得写成“真实性 N%”。|
|`score_type`|当前固定为 `heuristic_evidence_score`；可在提示中说明评分性质。|
|`verification_coverage`|显示为“已覆盖可核验主张比例”，不是事实正确率。|
|`verifiable_claim_count/determinate_claim_count`|显示为可核验主张数和形成确定性结果的主张数。|

`overall_verdict` 与 `claim_results[].verdict` 的真实枚举：

|值|中文|
|---|---|
|`supported`|多来源支持|
|`contradicted`|存在反驳证据|
|`conflicting`|来源说法冲突|
|`insufficient_evidence`|证据不足|
|`not_verifiable`|当前不可核验|

### 3.2 主张明细

- 用 `claim_results[].claim` 作为主张标题，`explanation` 作为解释。
- 用 `independent_source_count` 展示独立来源数量。
- `evidence[]` 显示 `source`、`quote`、URL 跳转和 `stance`；`stance` 真实枚举为 `supports`（支持）、`contradicts`（反驳）。
- `context_evidence[]` 显示补充上下文；`relation` 真实枚举为 `related`（相关但不足以定论）、`updates`（后续信息更新）。它们不应被画成支持或反驳评分。
- `limitations`、`risk_flags` 显示为说明标签；`reason_code` 是非封闭字符串，前端可原样作为技术提示，不应把它当作稳定中文文案来源。

### 3.3 核验 risk_flags 映射

|值|中文说明|
|---|---|
|`duplicate_or_reprint_evidence_removed`|重复或转载证据已去重。|
|`near_duplicate_with_fact_difference`|高相似材料存在关键事实差异。|
|`evolving_information`|材料可能反映信息演化。|
|`conflicting_evidence`|存在相互冲突的证据。|
|`limited_independent_sources`|独立来源数量有限。|
|`untrusted_instruction_ignored`|材料中疑似指令已作为数据忽略。|
|`no_verifiable_claims`|没有可核验主张。|
|`verification_input_truncated`|输入在核验上限处被截断。|

## 4. 证据图谱页面

### 4.1 顶部指标

使用 `metrics` 显示：`article_count`、`source_count`、`independent_source_count`、`claim_count`、`claim_cluster_count`、`support_edge_count`、`contradiction_edge_count`、`update_edge_count`、`duplicate_article_count`。

`conflict_ratio` 是冲突主张簇占可核验主张簇的比例；`reprint_ratio` 是转载比例；`unresolved_claim_ratio` 是未解决可核验主张簇比例；`contradiction_edge_ratio` 是逻辑关系边中的反驳比例。它们都是当前图结构指标，不是真实性概率。

`logical_edge_count` 用于完整逻辑关系统计，`returned_edge_count` 是当前响应返回的边数，`omitted_relation_edge_count` 与 `omitted_edge_count_by_type` 说明因展示上限未返回的语义关系边。基础结构边不受该上限影响。

### 4.2 ECharts 关系图与详情抽屉

- `nodes[].node_id` 作为 ECharts 节点 ID，`label` 用于节点文本，`node_type` 用于颜色/图标，`attributes` 放入详情抽屉。
- `edges[].source_node_id`、`target_node_id` 作为关系图 source/target；`edge_type` 映射为关系标签；`quote`、`reason_code`、`attributes` 用于详情抽屉。
- 所有节点和边 ID 都是服务端生成的稳定标识；不要从 ID 推断业务含义。

节点真实枚举：`event`（事件）、`article`（文章）、`source`（来源）、`claim`（原子主张）。

边真实枚举：

|值|中文|
|---|---|
|`contains`|事件包含文章|
|`published_by`|文章由来源发布|
|`asserts`|文章提出主张|
|`supports`|主张互相支持|
|`contradicts`|主张相互反驳|
|`updates`|后续主张更新较早主张|
|`duplicates`|文章为转载或高度重复材料|

关系边的 `attributes.independent_sources` 表示当前能否确认两端为独立来源；`source_independence_known` 为 `false` 时，不能将该关系用于独立来源结论。

### 4.3 时间线与主张簇

- 时间线使用 `timeline[].time` 显示，`time_source` 真实枚举为 `reference_time`（事实参考时间）、`event_time`（事件发生时间）、`publish_time`（文章发布时间）。
- `time_precision` 真实枚举为 `full_datetime`、`full_date`、`month_day_time`、`month_day`、`time_only`、`publish_datetime`；前端可显示为“完整日期时间/完整日期/月日时刻/月日/仅时刻/文章发布时间”。
- `year_inferred=true` 时，`normalized_time` 是服务端用于排序的推断完整时间；仍优先展示原始规范化 `time`，并加“年份推断”提示。
- `claim_clusters[]` 列表显示 `claim_type`、`canonical_slots`、`certainty_values`、各独立来源计数和 `status`。`claim_type`、`polarity`、`certainty` 不是封闭枚举，前端不应硬编码为接口契约。

主张簇 `status` 真实枚举：`supported`（独立来源支持）、`conflicting`（独立来源冲突）、`evolving`（信息演化）、`unresolved`（尚未形成稳定结论）、`not_verifiable`（不可核验）。

### 4.4 图谱 risk_flags 映射

|值|中文说明|
|---|---|
|`duplicate_reprints_present`|存在转载或高度重复文章。|
|`same_url_with_fact_difference`|相同 URL 材料包含不同关键事实。|
|`evidence_graph_input_truncated`|文章、主张、正文或关系展示受上限截断。|
|`missing_article_identifiers`|部分文章缺少可用编号，未参与跨文章关系校验。|
|`evidence_graph_relation_edges_truncated`|部分语义关系边未返回，但指标基于完整逻辑关系。|
|`conflicting_claims_present`|存在冲突主张簇。|
|`evolving_information`|存在信息演化关系。|
|`no_verifiable_graph_claims`|没有可核验图谱主张。|
|`unresolved_claims_present`|存在未解决主张簇。|
|`same_source_internal_inconsistency`|同一已知来源内部存在不一致说法。|
|`source_independence_unknown`|关系存在但来源独立性无法确认。|
|`untrusted_instruction_ignored`|材料中的疑似指令已作为数据忽略。|
|`no_graph_claims`|未提取到图谱主张。|

## 5. 空状态与错误状态

|场景|页面处理|
|---|---|
|无文章|报告、核验和图谱显示“当前事件暂无可用文章材料”；图谱响应可只有事件节点并带 `no_graph_claims`。|
|无独立来源|核验显示“独立来源不足”；图谱将 `independent_source_count` 显示为 0，并提示 `source_independence_unknown` 或相关局限。|
|无可核验主张|核验显示 `not_verifiable` 或 `no_verifiable_claims`；图谱显示 `no_verifiable_graph_claims`。|
|DeepSeek/Provider 不可用|问答与报告的 `503` 显示安全失败提示；核验和图谱不依赖 DeepSeek。|
|请求 `422`|显示“提交数据不符合接口要求”，提示检查必填字段、`max_claims` 范围与非空 `news_id` 唯一性。|
|目标新闻 `404`|仅核验页显示“待核验文章不在当前事件数据中”，提示刷新事件文章列表。|
