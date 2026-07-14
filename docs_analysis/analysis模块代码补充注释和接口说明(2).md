# analysis 模块代码补充注释和接口说明

本文档用于说明 4 号 NLP 智能分析模块的代码结构、调用方式、接口字段和小组对接边界。当前版本遵守 `接口规范4.0.md`，不删除既有返回字段，不改变 1/2/3/5 号接口。

## 一、模块定位

`analysis` 模块负责把后端传入的新闻数据转换为可展示、可存储、可用于后续报告和问答的智能分析结果。

模块主要完成：

- 文本清洗和字段标准化。
- 中文分词和关键词提取。
- 新闻摘要生成。
- 情感比例分析。
- 相似新闻检索，辅助后端做事件聚合。
- 热度指数、风险等级和生命周期阶段判断。
- 后端联调适配：从后端拉取待分析新闻，分析后按约定字段提交结果。

模块边界：

- `analysis` 不生成 `event_id`，最终事件 ID 由 1 号后端事件管理模块创建和维护。
- `similar_news` 只是辅助聚合同一事件的新闻编号列表，不代表 4 号模块已经完成最终事件聚合。
- `analysis` 不负责前端页面、事件详情报告、AI 问答结果或事件级趋势图。

## 二、模块调用入口

后端调用时推荐从统一入口进入：

```python
from analysis import analyze_news, analyze_news_batch
```

单条新闻分析：

```python
result = analyze_news(news, all_news=None, previous_heat_score=None)
```

批量新闻分析：

```python
results = analyze_news_batch(news_list, previous_heat_scores=None)
```

## 三、输入格式

单条新闻 `news` 建议包含以下字段：

```json
{
  "news_id": 1001,
  "title": "某地突发公共事件引发关注",
  "content": "新闻正文内容……",
  "source": "人民网",
  "url": "https://example.com/news/1001",
  "publish_time": "2026-07-08 10:00:00"
}
```

| 字段名 | 类型 | 是否必需 | 提供方 | 说明 |
| --- | --- | --- | --- | --- |
| `news_id` | int/string | 是 | 1 号后端 | 新闻唯一标识，用于结果回传和 `similar_news` 关联。 |
| `title` | string | 是 | 3 号爬虫/后端 | 新闻标题，用于正文分析、摘要生成和热度计算。 |
| `content` | string/text | 是 | 3 号爬虫/后端 | 新闻正文，是分词、关键词、情感和摘要分析的主要文本。 |
| `source` | string | 是 | 3 号爬虫/后端 | 新闻来源平台或媒体名称。 |
| `publish_time` | datetime string | 是 | 3 号爬虫/后端 | 新闻发布时间，建议格式为 `YYYY-MM-DD HH:MM:SS`。 |
| `url` | string | 是 | 3 号爬虫/后端 | 新闻原始链接，用于溯源、去重和详情跳转。 |

后端 `/internal/articles/pending` 返回的真实数据还可能包含以下增强字段：

| 字段名 | 类型 | 是否必需 | 说明 |
| --- | --- | --- | --- |
| `platform` | string | 否 | 平台名称，例如“微博”“新闻网站”。 |
| `crawl_time` | datetime string | 否 | 爬虫采集时间；当 `publish_time` 为空时，模块会把它作为内部时间特征使用。 |
| `created_at` | datetime string | 否 | 后端入库时间；当 `publish_time` 和 `crawl_time` 均为空时，可作为内部时间特征兜底。 |
| `repost_count` | number | 否 | 转发或转载量，用于热度计算。 |
| `comment_count` | number | 否 | 评论量，用于热度计算。 |
| `like_count` | number | 否 | 点赞量，用于热度计算。 |
| `account_id` / `account_name` / `account_type` | string/null | 否 | 账号相关信息，当前 4 号分析不直接生成新字段，但会保留在输入中供后端和 5 号使用。 |

说明：`publish_time` 仍是规范字段。若后端返回 `publish_time: null`，模块会在 `missing_fields` 中记录缺失，同时用 `crawl_time` 或 `created_at` 辅助相似度和生命周期计算；这只是内部降级，不会把采集时间伪装成新闻发布时间。

辅助参数：

| 参数名 | 类型 | 是否必需 | 说明 |
| --- | --- | --- | --- |
| `all_news` | list[dict] | 否 | 相似新闻候选集合，用于计算 `similar_news`。 |
| `previous_heat_score` | number/int/float | 否 | 同一事件上一时间点的热度值，通常由后端在事件聚合后提供。 |
| `news_list` | list[dict] | 批量分析时必需 | 批量分析的新闻列表，每个元素结构同 `news`。 |
| `previous_heat_scores` | dict | 否 | 批量分析时使用的历史热度映射，例如 `{1001: 80}`。 |

## 四、输出格式

`analyze_news()` 返回单条分析结果：

```json
{
  "news_id": 1001,
  "summary": "该新闻主要描述某地突发公共事件及其后续处置情况。",
  "processed_text": "清洗后的正文内容",
  "source": "人民网",
  "publish_time": "2026-07-08 10:00:00",
  "url": "https://example.com/news/1001",
  "missing_fields": [],
  "keywords": ["公共事件", "处置", "关注"],
  "sentiment": {
    "positive": 0.2,
    "neutral": 0.3,
    "negative": 0.5
  },
  "heat_score": 85,
  "stage": "高潮期",
  "risk_level": "高",
  "similar_news": [1002, 1003]
}
```

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| `news_id` | int/string | 原样返回新闻编号，便于后端更新对应记录。 |
| `summary` | string | 新闻摘要，由 4 号生成并返回后端，便于 5 号 AI 服务从后端获取事件摘要。 |
| `processed_text` | string | 清洗后的文本，供后端存储或调试使用。 |
| `source` | string | 标准化后的新闻来源。 |
| `publish_time` | string | 标准化后的发布时间。 |
| `url` | string | 标准化后的新闻链接。 |
| `missing_fields` | string[] | 记录缺失字段，用于提醒爬虫或后端补充数据。 |
| `keywords` | string[] | 高频关键词或核心词列表。 |
| `sentiment` | object | 情感倾向结果，包含 `positive`、`neutral`、`negative`。 |
| `heat_score` | number | 热度指数，范围 0 到 100。 |
| `stage` | string | 生命周期阶段预测。 |
| `risk_level` | string | 风险等级，取值为：低、中、高。 |
| `similar_news` | list | 相似新闻 `news_id` 列表，供 1 号后端做事件聚合参考。 |

说明：`news_id`、`source`、`publish_time`、`url`、`missing_fields` 继续回传，以保持 4.0 接口稳定，并方便后端保存、溯源和排查字段缺失问题。

## 五、整体调用链

```text
analyze_news()
  -> check_required_dependencies()
  -> preprocess_news()
  -> extract_keywords()
  -> generate_summary()
  -> analyze_sentiment()
  -> find_similar_news()
  -> calculate_heat_score()
  -> judge_risk_level()
  -> predict_lifecycle()
  -> 返回完整分析结果
```

后端联调脚本调用链：

```text
backend_sync.py
  -> GET /internal/articles/pending
  -> extract_news_list(response)，取 response["data"]
  -> analyze_news_batch(news_list)
  -> build_submit_payload(result)，只保留 7 个提交字段
  -> POST /internal/analysis
```

## 六、代码文件职责

| 文件 | 主要职责 |
| --- | --- |
| `analysis/__init__.py` | 统一导出外部可调用函数和依赖异常。 |
| `analysis/backend_sync.py` | 4 号联调脚本，主动调用后端 pending 接口，分析后提交到 `/internal/analysis`。 |
| `analysis/dependencies.py` | 检查 `jieba`、`SnowNLP`、`scikit-learn`，缺失时抛出 `AnalysisDependencyError`。 |
| `analysis/lexicon.py` | 统一加载内置词表和 `analysis/resources/` 中的外部扩展词表。 |
| `analysis/preprocess.py` | 文本清洗、元数据标准化、字段缺失检查、分词、数字过滤。 |
| `analysis/keyword_extract.py` | 使用 `jieba.analyse.extract_tags()` 提取关键词，并补充正文中命中的敏感词。 |
| `analysis/sentiment.py` | 使用 `SnowNLP` 分析正面、中性、负面比例，并用舆情敏感词对明显风险文本做纠偏。 |
| `analysis/similarity.py` | 使用 TF-IDF 和余弦相似度计算相似新闻。 |
| `analysis/heat_score.py` | 计算热度指数和风险等级。 |
| `analysis/lifecycle.py` | 预测生命周期阶段，输出 `stage`。 |
| `analysis/summary.py` | 生成新闻摘要 `summary`。 |

## 七、词表机制

当前新增 `analysis/resources/` 目录：

| 文件 | 用途 |
| --- | --- |
| `stopwords.txt` | 停用词扩展文件，用于过滤低价值词。 |
| `domain_words.txt` | 舆情领域词文件，会通过 `jieba.add_word()` 注入分词器。 |
| `sensitive_words.txt` | 敏感词文件，用于关键词补充、热度计算和摘要句子打分。 |

加载规则：

- `lexicon.py` 内置基础词表，保证没有外部文件时模块仍可运行。
- 外部词表存在时会与内置词表合并。
- 每行一个词，空行和 `#` 开头的注释行会被忽略。
- 外部词表不是第三方依赖，不影响 `jieba`、`SnowNLP`、`scikit-learn` 的强依赖检查。

## 八、预处理和数字保留

`preprocess.py` 当前处理逻辑：

- 清洗 HTML、URL、@用户、话题符号、零宽字符和明显噪声。
- 标准化 `source`、`publish_time`、`url`。
- 合并标题和正文，形成后续分析用的 `text`；如果正文已经以标题开头，则不重复拼接标题。
- 当 `publish_time` 缺失时，通过 `get_effective_time()` 按 `publish_time`、`crawl_time`、`created_at` 的顺序选择内部时间特征。
- 分词前把 `domain_words.txt` 中的领域词加入 `jieba`。
- 使用 `stopwords.txt` 和内置停用词过滤低价值词。

数字处理不再一刀切过滤：

- 保留带舆情价值的数字，例如 `3人`、`24小时`、`80%`、`2026年`、`1.2亿`、`5级`。
- 过滤孤立低价值纯数字，例如普通页码、无上下文序号、单独数字碎片。
- 数字不新增返回字段，只参与关键词、相似度和摘要评分。

## 九、关键词和敏感词

`keyword_extract.py` 继续使用 `jieba.analyse.extract_tags()` 提取关键词，同时会扫描正文中命中的敏感词。

当前关键词合并策略：

- 先从 `jieba.analyse.extract_tags()` 获取比 `top_k` 更多的候选关键词。
- 如果候选关键词本身包含敏感词，优先保留该关键词，例如“火灾事故”优先于单独的“火灾”。
- 如果敏感词出现在正文中，但没有被 jieba 选入候选关键词，会把该敏感词补入最终关键词列表。
- 最终仍按 `top_k` 截断，接口字段仍是 `keywords: string[]`，不新增字段。

敏感词不再只写死在代码里，而是通过 `load_sensitive_words()` 从内置词表和 `analysis/resources/sensitive_words.txt` 合并得到。

敏感词主要用于：

- `keyword_extract.py` 中补充敏感词，避免正文中明显敏感词被 TF-IDF 排名挤掉。
- `heat_score.py` 中计算敏感关键词命中得分。
- `summary.py` 中给候选摘要句子加权。

## 十、情感分析

`sentiment.py` 当前逻辑：

- 强依赖 `SnowNLP`。
- 使用 `SnowNLP(text).sentiments` 得到情感分数。
- 转换为 `positive`、`neutral`、`negative` 三类比例。
- 使用 `load_sensitive_words()` 和内置 `NEGATIVE_HINT_WORDS` 检查事故、台风、暴雨、自杀、预警等明显风险词。
- 如果文本命中风险提示词，而 SnowNLP 给出的 `negative` 过低，会把负面比例提升到合理下限：
  - 命中 1 个风险词：`negative` 至少约 `0.38`。
  - 命中 2 个风险词：`negative` 至少约 `0.50`。
  - 命中 3 个及以上风险词：`negative` 至少约 `0.60`。
- 校正后仍会重新归一化，保证三项比例总和接近 `1`。

这样做是为了适配微博舆情文本中常见的情况：例如“台风”“强降雨”“自杀身亡”“重大事故”等文本，SnowNLP 可能因为语料原因误判为高正面，模块会用舆情词表做保守纠偏。

## 十一、摘要生成优化

`summary.py` 不再只取正文第一句。

当前策略：

- 先将正文切分为候选句子。
- 根据关键词命中、敏感词命中、标题重合度和句子长度给候选句打分。
- 跳过与标题高度重复的句子，避免摘要重复。
- 选择得分最高的 1 到 2 个句子作为摘要主体。
- 关键词不再简单拼接后统一截断，而是为“关键词：...”预留长度，尽量保证关键词不会被截断丢失。

## 十二、热度、风险、生命周期

热度计算公式：

```text
similar_score = min(len(similar_news) * 25, 100)
keyword_score = min(sensitive_hits * 25, 100)
sentiment_score = min(max(positive, negative) * 100 + min(positive, negative) * 40, 100)
interaction_score = min(log10(repost_count * 3 + comment_count * 2 + like_count + 1) / 4 * 100, 100)

heat_score = similar_score * 0.35 + keyword_score * 0.20 + sentiment_score * 0.25 + interaction_score * 0.20
```

含义：

- `similar_score`：相似新闻数量得分，表示传播范围。
- `keyword_score`：敏感关键词命中得分，表示舆情敏感度；由于关键词提取阶段会补充正文命中的敏感词，漏算概率比单纯依赖 jieba Top-K 更低。
- `sentiment_score`：情绪强度得分，强正面和强负面都可以提高热度。
- `interaction_score`：互动量得分，优先级为转发量、评论量、点赞量，适配微博等平台的真实 pending 数据。
- `risk_level`：风险等级仍重点参考负面情绪，因为热度和风险不是同一个概念。

## 十三、依赖检查和错误处理

analysis 模块必须安装：

```text
jieba
snownlp
scikit-learn
```

安装命令：

```powershell
python -m pip install jieba snownlp scikit-learn
```

如果缺少依赖，模块会抛出 `AnalysisDependencyError`，不会返回半成品 JSON，也不会静默使用简单规则兜底。

## 十四、小组对接说明

### 与 1 号后端

常规函数调用时，后端需要传入：

- `news_id`
- `title`
- `content`
- `source`
- `publish_time`
- `url`

后端建议保存：

- `summary`：给 5 号 AI 报告和问答使用。
- `keywords`：给前端展示高频词。
- `sentiment`：给前端画情感分布图。
- `heat_score`：给事件看板排序。
- `risk_level`：给首页或事件看板做风险提示。
- `stage`：给事件详情页展示生命周期。
- `similar_news`：给后端做事件聚合参考。
- `source`、`publish_time`、`url`、`missing_fields`：用于溯源、排查和字段补齐。

联调脚本对接时，1 号后端提供：

- `GET /internal/articles/pending`：返回 `{code, message, data}`，其中 `data` 是待分析新闻列表。
- `POST /internal/analysis`：接收 4 号分析结果。

注意：传给 `analyze_news_batch()` 的必须是 `response["data"]`，不是整个 `{code, message, data}` 外层对象。

### 与 3 号爬虫

爬虫需要尽量保证字段完整：

- `title` 不能为空，否则关键词和摘要效果会下降。
- `content` 不能为空，否则情感分析和相似度计算会下降。
- `source` 要统一平台名称，例如“人民网”“微博”“央视新闻”。
- `publish_time` 尽量使用统一格式，例如 `2026-07-09 10:30:00`。
- `url` 应保留原始新闻链接，方便后续溯源。

如果字段缺失，模块会在 `missing_fields` 中返回缺失字段名，方便后端或爬虫排查。

### 与 5 号 AI 应用

5 号可以从后端读取以下分析结果作为报告或问答上下文：

```text
事件摘要：{summary}
关键词：{keywords}
情感分布：{sentiment}
风险等级：{risk_level}
生命周期：{stage}
相似新闻：{similar_news}
```

## 十五、后端联调脚本说明

`analysis/backend_sync.py` 用于 4 号和 1 号后端联调，不新增自己的后端接口，而是主动调用组长提供的接口。

默认后端地址：

```text
http://10.122.240.155:8000
```

脚本支持两种运行位置。

在项目根目录运行：

```powershell
python -m analysis.backend_sync --base-url http://10.122.240.155:8000 --dry-run --limit 1
```

在 `analysis/` 目录内运行：

```powershell
python backend_sync.py --base-url http://10.122.240.155:8000 --dry-run --limit 1
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `--base-url` | 后端服务地址，默认 `http://10.122.240.155:8000`。 |
| `--from-file` | 从本地保存的 pending 响应 JSON 读取数据，用于离线测试。 |
| `--dry-run` | 只打印将提交的 JSON，不写入后端；这是默认安全模式。 |
| `--submit` | 真实提交到 `POST /internal/analysis`。 |
| `--limit` | 每次最多处理多少条，默认 `1`；`0` 表示处理全部。 |
| `--loop` | 持续轮询 pending 接口。 |
| `--interval` | 轮询间隔秒数，默认 `60`。 |
| `--timeout` | HTTP 超时时间，默认 `10` 秒。 |

离线测试：

```powershell
python -m analysis.backend_sync --from-file C:\Users\33087\Downloads\response_1783832687173.json --dry-run --limit 1
```

真实提交 1 条：

```powershell
python -m analysis.backend_sync --base-url http://10.122.240.155:8000 --submit --limit 1
```

每分钟轮询提交：

```powershell
python -m analysis.backend_sync --base-url http://10.122.240.155:8000 --submit --loop --interval 60
```

脚本提交前会通过 `build_submit_payload()` 过滤字段，只向后端提交：

```json
{
  "news_id": 21,
  "keywords": ["关键词1", "关键词2"],
  "sentiment": {
    "positive": 0.6,
    "neutral": 0.3,
    "negative": 0.1
  },
  "heat_score": 80,
  "stage": "成长期",
  "risk_level": "中",
  "similar_news": []
}
```

不会提交 `summary`、`processed_text`、`source`、`publish_time`、`url`、`missing_fields` 等调试或辅助字段。

## 十六、demo 文件说明

完整流程演示：

```powershell
python -m analysis.demo
```

预处理演示：

```powershell
python -m analysis.preprocess_demo
```

如果依赖未安装，demo 会提示缺少依赖并退出。

## 十七、当前注意事项

- 返回字段遵守 `接口规范4.0.md`，不删除 `news_id`、`source`、`publish_time`、`url`、`missing_fields`。
- 后端联调提交时遵守 `/internal/analysis` 的严格字段要求，只提交 `news_id`、`keywords`、`sentiment`、`heat_score`、`stage`、`risk_level`、`similar_news`。
- `tokens` 和 `token_count` 是 `preprocess.py` 内部结果，按当前对接要求不返回给 1 号后端。
- `lifecycle_prediction` 字段已经不再单独输出，生命周期预测统一使用 `stage` 字段。
- `previous_heat_score` 当前多数情况下会是 `None`，因为 4 号输入是新闻 `news`，不负责确定 `event_id`。
- `similar_news` 是辅助聚合信号，不等于最终 `event_id`，也不代表 4 号完成了事件合并。
