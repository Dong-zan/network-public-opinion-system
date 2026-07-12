# AI Service

成员 5 的独立 AI 服务。当前包含基于单个舆情事件上下文的单轮智能问答和智能事件分析报告。

## 当前能力

- `GET /health`：服务健康检查。
- `POST /ai/ask`：基于 1 号后端传入的 `EventContext` 回答事件概述、风险解释、情感、媒体来源、具体文章和趋势限制等问题。
- `POST /ai/report`：基于同一 `EventContext` 生成结构化的事件概述、整体总结、趋势解释、风险解释、建议和局限说明。
- 智能问答与智能报告是两个独立功能，只共享 EventContext、Provider、配置和统一异常边界。
- 当前业务规则、问题分类和文章 Top-K 检索能力已经实现。
- 默认使用稳定、离线的 `FakeLLMProvider`，仅用于测试和离线联调，不访问网络，也不需要 API Key。
- 可显式切换到 `DeepSeekProvider`，使用 OpenAI-compatible SDK 调用 `deepseek-v4-flash`。
- 文章输入可以是事件下的全部新闻；服务会按问题筛选相关上下文，不会把全部正文直接送入 Provider。
- Fake 模式下，普通开放式问题返回相关证据整理；DeepSeek 模式下返回模型生成的最终普通文本。
- 当前调用为非流式、单轮事件问答，默认关闭思考模式。
- 报告接口在 DeepSeek 模式下要求模型返回 JSON，并通过 Pydantic 校验；结构错误最多安全修复一次。
- 图表不由大模型生成。完整详情页由前端组合结构化图表数据和 AI 报告文字。

## 当前不包含

- 可信度评估
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
DEEPSEEK_MAX_TOKENS=1000
DEEPSEEK_TEMPERATURE=0.2
AI_REPORT_TOP_K=5
AI_REPORT_ARTICLE_MAX_CHARS=1000
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
