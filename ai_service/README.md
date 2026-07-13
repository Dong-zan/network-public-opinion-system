# AI Service

成员 5 的独立 AI 服务。当前包含基于单个舆情事件上下文的单轮智能问答、智能事件分析报告、多来源事实核验和可解释证据图谱第一阶段。

## 当前能力

- `GET /health`：服务健康检查。
- `POST /ai/ask`：基于 1 号后端传入的 `EventContext` 回答事件概述、风险解释、情感、媒体来源、具体文章和趋势限制等问题。
- `POST /ai/report`：基于同一 `EventContext` 生成结构化的事件概述、整体总结、趋势解释、风险解释、建议和局限说明。
- `POST /ai/verify`：在当前事件输入的文章范围内，按原子事实主张执行确定性的多来源证据核验。
- `POST /ai/evidence-graph`：确定性构建事件、文章、来源和原子主张图谱，并返回证据关系、主张簇、演化时间线及可解释结构指标。
- 智能问答与智能报告是两个独立功能，只共享 EventContext、Provider、配置和统一异常边界。
- 当前业务规则、问题分类和文章 Top-K 检索能力已经实现。
- 默认使用稳定、离线的 `FakeLLMProvider`，仅用于测试和离线联调，不访问网络，也不需要 API Key。
- 可显式切换到 `DeepSeekProvider`，使用 OpenAI-compatible SDK 调用 `deepseek-v4-flash`。
- 文章输入可以是事件下的全部新闻；服务会按问题筛选相关上下文，不会把全部正文直接送入 Provider。
- Fake 模式下，普通开放式问题返回相关证据整理；DeepSeek 模式下返回模型生成的最终普通文本。
- 当前调用为非流式、单轮事件问答，默认关闭思考模式。
- 报告接口在 DeepSeek 模式下要求模型返回 JSON，并通过 Pydantic 校验；结构错误最多安全修复一次。
- 图表不由大模型生成。完整详情页由前端组合结构化图表数据和 AI 报告文字。
- 第一阶段核验不调用 Provider、不联网，不使用模型自报置信度；`evidence_score` 是启发式证据评分，不代表事实为真的概率。
- 第一阶段证据图谱不调用 Provider；转载文章保留图节点，但不会增加独立来源数量，结构比例也不表示真实性概率。

## 当前不包含

- 联网事实核查和外部权威数据库检索
- 传播路径分析
- 多轮对话
- 流式输出
- 工具调用和联网搜索
- 数据库读写

## 安装依赖

建议使用 Python 3.10 或更高版本，并在 `ai_service/` 目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## 启动服务

默认 Fake 模式无需额外配置，在 `ai_service/` 目录执行：

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8005
```

启动后可访问 `http://127.0.0.1:8005/health`。

## 运行测试

在 `ai_service/` 目录执行：

```powershell
pytest
```

测试默认使用 `FakeLLMProvider` 或 mock，不访问网络。Fake 模式下 `/ai/report` 返回稳定的规则报告，便于离线联调。

## Provider 配置

默认配置是：

```text
AI_LLM_PROVIDER=fake
```

Fake 模式离线运行，不需要 API Key，不消耗 DeepSeek 额度。

切换到 DeepSeek 时，在 `ai_service/` 下从 `.env.example` 创建本地 `.env`，至少配置：

```text
AI_LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=<本地填写，不得提交>
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_THINKING_ENABLED=false
DEEPSEEK_TIMEOUT_SECONDS=45
DEEPSEEK_MAX_TOKENS=3000
DEEPSEEK_TEMPERATURE=0.2
AI_REPORT_TOP_K=5
AI_REPORT_ARTICLE_MAX_CHARS=1000
AI_VERIFY_MAX_CANDIDATES=50
AI_VERIFY_MAX_SENTENCES_PER_ARTICLE=100
AI_VERIFY_ARTICLE_MAX_CHARS=5000
AI_EVIDENCE_GRAPH_MAX_ARTICLES=50
AI_EVIDENCE_GRAPH_MAX_CLAIMS_PER_ARTICLE=5
AI_EVIDENCE_GRAPH_MAX_EDGES=500
AI_EVIDENCE_GRAPH_ARTICLE_MAX_CHARS=5000
```

`.env` 已被 `.gitignore` 排除。源码、测试、日志和 API 响应都不应包含真实密钥。`AI_LLM_PROVIDER` 只接受 `fake` 或 `deepseek`，其他值会明确报错；选择 `deepseek` 但密钥为空也会在初始化时失败，不会回退到 Fake。

使用 `.env` 启动 DeepSeek 模式：

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8005 --env-file .env
```

思考模式默认关闭。若将 `DEEPSEEK_THINKING_ENABLED` 设置为 `true`，请求不会继续发送 `temperature`。

## 手动真实 API 联调

1. 在本地 `.env` 中填写真实 `DEEPSEEK_API_KEY`，确认该文件没有被 Git 跟踪。
2. 使用上面的 `--env-file .env` 命令启动服务。
3. 先访问 `GET /health`，再向 `POST /ai/ask` 发送开放式问题，或向 `POST /ai/report` 发送完整 EventContext。
4. DeepSeek 模式下的开放式问答和报告生成会消耗 API 额度；问答中的风险、情感、来源、指定文章和缺少时间序列的趋势问题不调用模型。
5. 联调结束后停止服务，不要把 `.env`、请求头或密钥粘贴到日志、测试和提交记录中。

自动测试全部使用 Fake 或 mock 客户端，不会发出真实 DeepSeek 请求，也不会消耗 API 额度。

## /ai/verify 语义校准（仅离线开发）

`semantic_assessment` 是可选增强结果，默认 `AI_VERIFY_SEMANTIC_ENABLED=false`。它不会参与 `overall_verdict`、`claim_results`、`evidence_score`、可信度 `risk_score`、`risk_label`、`assessment_confidence` 或第一阶段确定性摘要。

仓库内的 `tests/fixtures/verification_semantic_calibration.json` 使用虚构、脱敏文章和预置候选输出。运行 Validator 离线评测：

```powershell
python scripts/evaluate_verification_semantic.py --mode fixture-validator
```

人工校准真实模型时：

1. 确认默认语义开关关闭，只准备脱敏、虚构的测试文章。
2. 在个人本地环境临时启用语义功能，人工调用模型并仅保存其原始 JSON 输出。
3. 输出按 `{"outputs":[{"case_id":"...","output":{...}}]}` 保存到 `local_calibration_outputs/`；该目录已被 Git 忽略。
4. 关闭语义功能，使用以下命令离线计算指标：

```powershell
python scripts/evaluate_verification_semantic.py `
  --mode saved-output `
  --saved-output local_calibration_outputs/deepseek-output.json `
  --report local_calibration_outputs/evaluation-report.json
```

评测脚本不会创建 Provider 或访问网络。不得提交真实 `.env`、API Key、真实用户新闻、完整敏感 Prompt 或真实模型输出。

进入第二阶段 B 前，建议人工校准达到：复杂风险总体 precision 不低于 0.85；`preliminary_as_confirmed` 和 `title_body_mismatch` precision 不低于 0.90；`unsupported_causality` precision 不低于 0.80；中性案例误报率不高于 0.10；Schema/fallback 比例处于可接受范围。fixture-validator 的确定性准入要求 precision 为 1.0，且伪造 quote、错误 evidence news_id 和不存在 claim id 均不得通过。这些阈值只用于开发验收，不会自动改变业务评分。

## 多来源事实核验边界

`/ai/verify` 以目标文章中的原子事实主张为核验单位，不对整篇文章简单判定真假。目标文章不能作为自己的支持证据；候选证据会按文章编号、URL、相同正文和正文相似度处理。高相似正文只有在关键事实签名一致时才去重，数字、地点、时间、伤亡类型、原因或状态不同的近似报道会保留用于识别潜在冲突。最终证据引用必须逐字存在于输入文章正文，文章编号、来源和 URL 均从 `EventContext` 回填。

第一阶段支持伤亡类型与数量、地点、事件时间、原因、处置状态、调查结论、已确认与尚未确认状态、独立来源数量和确定性结论汇总。它只处理请求中提供的事件文章，不进行联网搜索，也不将“仍在调查”视为具体原因已经证实。

内部主张将认识状态和命题正负分开处理，并完整保留可识别的事件日期、时间和日期时间。伤亡数量、处置状态和调查结论等可变化事实会结合文章发布时间判断信息演化；较晚报道中的合理进展不会自动作为对较早报道的反驳。文章发布时间只用于判断报道先后，不会被当作事件发生时间。

独立来源按规范化来源名称、URL hostname 和转载关系保守聚类：来源名相同或 hostname 相同均只计一个来源簇。核验请求中的非空 `news_id` 必须唯一，重复编号会返回422，避免证据正文和来源被覆盖。

`evidence_score` 表示系统对当前整体核验结论的启发式证据强度。评分只聚合支撑 `overall_verdict` 的对应主张，不会因大量无结论主张被简单平均稀释；覆盖不足由 `verification_coverage` 和 `limitations` 表达。高分必须与 `overall_verdict` 一起阅读：高分配合 `contradicted` 表示反驳证据较强，并不表示目标文章更真实。该分数不是新闻真实性概率，也不是模型自报置信度。

核验默认最多处理50篇候选文章、每篇100个句子和每篇5000个字符。超过 `AI_VERIFY_MAX_CANDIDATES`、`AI_VERIFY_MAX_SENTENCES_PER_ARTICLE` 或 `AI_VERIFY_ARTICLE_MAX_CHARS` 时会按输入顺序确定性截断，并在 `limitations` 中说明。

## 可解释证据图谱边界

`/ai/evidence-graph` 直接复用原子主张提取、立场分类、引用校验、来源聚类和转载识别能力，不通过 HTTP 调用 `/ai/verify`。图谱包含事件、文章、来源和主张节点，以及归属、发布、断言、支持、反驳、更新和转载关系。所有关系引用必须逐字存在于输入文章正文。

主张簇优先使用 `claim_type`、规范化槽位、极性和确定性构建，参考时间单独用于演化排序。时间线依次优先使用主张参考时间、事件发生时间和文章发布时间；使用发布时间时会明确标记为 `publish_time`，不会伪装成事件发生时间。

默认最多处理50篇文章、每篇5条主张、500条语义关系边和每篇5000字符。`AI_EVIDENCE_GRAPH_MAX_EDGES` 只限制 `supports`、`contradicts`、`updates` 的返回数量；`contains`、`published_by`、`asserts`、`duplicates` 等基础结构边始终完整返回。超过 `AI_EVIDENCE_GRAPH_MAX_ARTICLES`、`AI_EVIDENCE_GRAPH_MAX_CLAIMS_PER_ARTICLE`、`AI_EVIDENCE_GRAPH_MAX_EDGES` 或 `AI_EVIDENCE_GRAPH_ARTICLE_MAX_CHARS` 时会确定性截断并写入 `limitations`。冲突比例、转载比例和未解决主张比例只描述当前输入形成的图结构，不是真实性概率。

## 报告与图表边界

`/ai/report` 只生成文字和结构化报告字段，不生成图片、折线图、饼图或词云，也不重新计算上游算法结果。详情页图表继续使用：

- 报道趋势：`articles[].publish_time`
- 情感分布：`analysis.sentiment`
- 平台分布：`articles[].platform`
- 高频关键词：`analysis.keywords`

前端负责把这些结构化图表数据与 `/ai/report` 返回的报告文字组合展示。

报告文章选择独立使用 `AI_REPORT_TOP_K` 和 `AI_REPORT_ARTICLE_MAX_CHARS`，不会复用或改变问答的 `AI_QA_TOP_K`、`AI_ARTICLE_MAX_CHARS`。模型 JSON 通过 Schema 后，服务端仍会核对事件时间、地点、人物和原因是否有选中文章正文支持；无证据字段会被保守清除并写入 `limitations`。最终趋势和风险解释由服务端根据上游结构化输入确定性生成，不直接采用模型结论。

## 接口示例

健康检查：

```http
GET /health
```

智能问答：

```http
POST /ai/ask
Content-Type: application/json

{
  "event": {
    "event_id": 1,
    "title": "事件标题",
    "summary": "事件摘要",
    "update_time": "2026-07-08 12:00:00",
    "articles": [],
    "analysis": {
      "keywords": ["事故", "救援"],
      "sentiment": {
        "positive": 0.2,
        "neutral": 0.3,
        "negative": 0.5
      },
      "heat": 85,
      "stage": "高潮期",
      "risk_level": "高"
    }
  },
  "question": "这个事件的主要风险点是什么？"
}
```

响应只公开 `answer`：

```json
{
  "answer": "基于当前事件上下文生成的回答"
}
```

智能报告：

```http
POST /ai/report
Content-Type: application/json

{
  "event": {
    "event_id": 1,
    "title": "事件标题",
    "summary": "事件背景摘要",
    "update_time": "2026-07-08 12:00:00",
    "articles": [],
    "analysis": {
      "keywords": [],
      "sentiment": {},
      "heat": 85,
      "stage": "高潮期",
      "risk_level": "高"
    }
  }
}
```

报告响应包含：

```json
{
  "overview": {
    "time": null,
    "location": null,
    "cause": null,
    "persons": [],
    "summary": "事件概述"
  },
  "summary": "事件整体总结",
  "trend_analysis": "趋势文字解释",
  "risk_analysis": "风险解释",
  "suggestions": ["建议一", "建议二"],
  "limitations": ["数据不足说明"]
}
```

多来源事实核验：

```http
POST /ai/verify
Content-Type: application/json

{
  "event": {
    "event_id": 1,
    "title": "事件标题",
    "summary": "事件背景摘要",
    "articles": [
      {
        "news_id": 1001,
        "title": "待核验报道",
        "content": "事故造成3人受伤。",
        "source": "媒体甲",
        "url": "https://example.com/1001"
      }
    ],
    "analysis": {}
  },
  "target_news_id": 1001,
  "max_claims": 5
}
```

核验响应中的 `overall_verdict` 和每条主张结论使用 `supported`、`contradicted`、`conflicting`、`insufficient_evidence` 或 `not_verifiable`。`score_type` 固定为 `heuristic_evidence_score`。响应还提供可核验主张数、确定结论数、核验覆盖率和评分解释；这些新增字段不改变原有字段。
