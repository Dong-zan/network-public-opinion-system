# analysis 模块代码补充注释和接口说明

本文档整合原 `analysis代码补充注释（给小组看）.docx` 和 `analysis接口格式记录（给组长看）.docx` 的内容，用于说明 4 号 NLP 智能分析模块的代码结构、调用方式、接口字段和小组对接边界。

## 一、模块定位

`analysis` 模块负责把后端传入的新闻数据转换为可展示、可存储、可用于后续报告和问答的智能分析结果。

模块主要完成：

- 文本清洗和字段标准化。
- 中文分词和关键词提取。
- 新闻摘要生成。
- 情感比例分析。
- 相似新闻检索，辅助后端做事件聚合。
- 热度指数、风险等级和生命周期阶段判断。

模块边界：

- `analysis` 不生成 `event_id`，最终事件 ID 由 1 号后端事件管理模块创建和维护。
- `similar_news` 只是辅助聚合同一事件的新闻编号列表，不代表 4 号模块已经完成最终事件聚合。
- `analysis` 不负责前端页面、事件详情报告、AI 问答结果或事件级趋势图。

## 二、模块调用入口

后端调用时推荐从统一入口进入，不直接调用内部算法文件：

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
| `source` | string | 是 | 3 号爬虫/后端 | 新闻来源平台或媒体名称，例如微博、澎湃新闻、人民网。 |
| `publish_time` | datetime string | 是 | 3 号爬虫/后端 | 新闻发布时间，建议格式为 `YYYY-MM-DD HH:MM:SS`，用于相似新闻和生命周期判断。 |
| `url` | string | 是 | 3 号爬虫/后端 | 新闻原始链接，用于溯源、去重和详情跳转。 |

辅助参数：

| 参数名 | 类型 | 是否必需 | 说明 |
| --- | --- | --- | --- |
| `all_news` | list[dict] | 否 | 相似新闻候选集合，用于计算 `similar_news`。每条候选新闻建议包含 `news_id`、`title`、`content`、`source`、`publish_time`、`url`。 |
| `previous_heat_score` | number/int/float | 否 | 同一事件上一时间点的热度值。由于 4 号无法确定 `event_id`，该值通常由 1 号后端在事件聚合后提供；没有历史值时传 `None`。 |
| `news_list` | list[dict] | 批量分析时必需 | 批量分析的新闻列表，每个元素结构同 `news`。 |
| `previous_heat_scores` | dict | 否 | 批量分析时使用的历史热度映射，例如 `{1001: 80}`，key 为 `news_id`，value 为历史热度。 |

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
| `sentiment` | object | 情感倾向结果，包含 `positive`、`neutral`、`negative` 三个 0 到 1 的比例值。 |
| `heat_score` | number | 热度指数，范围 0 到 100。 |
| `stage` | string | 生命周期阶段预测，取值建议为：潜伏期、成长期、高潮期、衰退期。 |
| `risk_level` | string | 风险等级，取值为：低、中、高。 |
| `similar_news` | list | 相似新闻 `news_id` 列表，供 1 号后端做事件聚合参考。 |

明确不由 `analysis` 返回的内容：

| 字段/功能 | 是否由 analysis 返回 | 说明 |
| --- | --- | --- |
| `event_id` | 否 | 由 1 号后端事件管理模块生成和维护。4 号只提供 `similar_news` 作为聚合参考。 |
| `tokens` / `token_count` | 否 | 只作为 `analysis` 内部处理信息，不返回给 1 号后端。 |
| `overview` / `timeline` / `trend` / `platform_distribution` | 否 | 属于事件级看板或报告字段，需要由后端聚合多条新闻后生成。 |
| `ai_report` / `answer` | 否 | 属于 5 号 AI 服务模块。 |

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

| 步骤 | 函数 | 作用 | 输出给下一步的内容 |
| --- | --- | --- | --- |
| 1 | `check_required_dependencies()` | 检查 `jieba`、`SnowNLP`、`scikit-learn` 是否可用。 | 缺依赖时抛出 `AnalysisDependencyError`。 |
| 2 | `preprocess_news()` | 清洗新闻标题、正文、来源、时间、链接，并检查缺失字段。 | `processed_text`、`source`、`publish_time`、`url`、`missing_fields`。 |
| 3 | `extract_keywords()` | 从清洗文本中提取关键词。 | `keywords`。 |
| 4 | `generate_summary()` | 根据标题、正文首句、来源、时间和关键词生成摘要。 | `summary`。 |
| 5 | `analyze_sentiment()` | 计算正面、中性、负面情感比例。 | `sentiment`。 |
| 6 | `find_similar_news()` | 从候选新闻中找出相似新闻编号。 | `similar_news`。 |
| 7 | `calculate_heat_score()` | 综合相似新闻数量、敏感关键词和情绪强度计算热度。 | `heat_score`。 |
| 8 | `judge_risk_level()` | 根据热度和负面情绪给出风险等级。 | `risk_level`。 |
| 9 | `predict_lifecycle()` | 根据热度、相似新闻、平台数、时间跨度预测生命周期阶段。 | `stage`。 |

## 六、代码文件职责

| 文件 | 主要职责 | 给谁调用 |
| --- | --- | --- |
| `analysis/__init__.py` | 统一导出 `analyze_news`、`analyze_news_batch`、`preprocess_news`、`preprocess_news_batch`、`generate_summary`，以及依赖检查相关异常。 | 后端或其他模块导入 `analysis` 包时使用。 |
| `analysis/dependencies.py` | 统一检查 `jieba`、`SnowNLP`、`scikit-learn`，缺失时抛出 `AnalysisDependencyError`。 | pipeline 和内部算法函数调用。 |
| `analysis/analysis_pipeline.py` | 总流程编排文件，把预处理、关键词、摘要、情感、相似新闻、热度、风险、生命周期串起来。 | 最主要入口，1 号后端应优先调用这里。 |
| `analysis/preprocess.py` | 负责文本清洗、元数据标准化、字段缺失检查、分词。 | pipeline、关键词、相似度、摘要、生命周期都会间接依赖它。 |
| `analysis/keyword_extract.py` | 负责关键词提取，使用 `jieba.analyse.extract_tags()`。 | pipeline 调用。 |
| `analysis/sentiment.py` | 负责情感倾向分析，使用 `SnowNLP`。 | pipeline 调用。 |
| `analysis/similarity.py` | 负责相似新闻检索，结合文本相似度、时间、来源和链接域名。 | pipeline 调用，输出给后端事件聚合参考。 |
| `analysis/heat_score.py` | 负责热度指数和风险等级计算。 | pipeline 调用。 |
| `analysis/lifecycle.py` | 负责生命周期阶段预测，输出 `stage`。 | pipeline 调用。 |
| `analysis/summary.py` | 负责新闻摘要生成，返回 `summary` 给后端保存，便于 5 号 AI 服务读取。 | pipeline 调用，也可单独调用。 |
| `analysis/demo.py` | 完整流程演示，模拟多条新闻输入。 | 本地自测使用，不是正式接口。 |
| `analysis/preprocess_demo.py` | 预处理演示，只测试清洗、标准化、分词和缺失字段。 | 本地自测使用，不是正式接口。 |

## 七、核心函数和变量说明

### 7.1 入口函数

| 函数/变量 | 含义 | 调用逻辑 |
| --- | --- | --- |
| `analyze_news(news, all_news=None, previous_heat_score=None)` | 分析单条新闻并返回后端约定字段。 | 先检查依赖，再依次调用预处理、关键词、摘要、情感、相似新闻、热度、风险和生命周期函数。 |
| `analyze_news_batch(news_list, previous_heat_scores=None)` | 批量分析新闻列表。 | 对 `news_list` 中每条新闻循环调用 `analyze_news()`，并把整批 `news_list` 作为 `all_news` 传入。 |
| `all_news` | 当前批次所有新闻。 | 主要服务 `similar_news` 和生命周期判断；如果单条调用时没有传入，默认 `all_news = [news]`。 |
| `previous_heat_score` | 同一事件上一时间点热度。 | 通常由后端在事件聚合并保存历史热度后提供；没有时为 `None`。 |

### 7.2 预处理

| 函数/变量 | 功能说明 | 关键输入输出 |
| --- | --- | --- |
| `REQUIRED_FIELDS` | 规定一条新闻必须包含的字段。 | `news_id`、`title`、`content`、`source`、`publish_time`、`url`。 |
| `STOPWORDS` | 停用词集合，用于过滤无实际分析意义的词。 | 在 `tokenize()` 中使用。 |
| `DOMAIN_WORDS` | 舆情领域词集合。 | 保留为项目词表说明，不再作为缺依赖时的兜底分词方案。 |
| `clean_text(text)` | 去除 HTML 标签、URL、多余空格、@用户、话题符号和明显噪声。 | 输入原始字符串，输出清洗后的字符串。 |
| `normalize_source(source)` | 标准化新闻来源。 | 去掉多余空格和结尾标点。 |
| `normalize_url(url)` | 标准化新闻链接。 | 只做字符串清理，不访问网络验证链接。 |
| `normalize_publish_time(publish_time)` | 标准化发布时间。 | 支持 `datetime`、`date` 和字符串，尽量转成稳定时间字符串。 |
| `merge_title_content(news)` | 合并标题和正文。 | 标题和正文都存在时拼接，使标题在后续分析中有更高权重。 |
| `tokenize(text)` | 分词并过滤短词、纯数字和停用词。 | 使用 `jieba.lcut()`；如果缺少 `jieba`，抛出 `AnalysisDependencyError`。 |
| `find_missing_fields(news)` | 检查必要字段是否为空。 | 返回缺失字段列表，例如 `["url"]`。 |
| `preprocess_news(news)` | 预处理单条新闻。 | 返回清洗后的字段、合并文本、分词结果和缺失字段。 |

### 7.3 关键词、摘要、情感

| 文件 | 函数/变量 | 说明 |
| --- | --- | --- |
| `keyword_extract.py` | `SENSITIVE_WORDS` | 敏感舆情词集合，用于热度计算中的敏感关键词命中。 |
| `keyword_extract.py` | `extract_keywords(text, top_k=5)` | 使用 `jieba.analyse.extract_tags()` 从正文提取关键词；缺少 `jieba` 时抛出 `AnalysisDependencyError`。 |
| `summary.py` | `_split_sentences(text)` | 把正文切分成候选句子，通常取第一句作为摘要主体。 |
| `summary.py` | `_trim_text(text, max_length)` | 限制摘要长度，避免返回过长文本。 |
| `summary.py` | `_source_phrase(source)` | 把来源处理成自然表达，例如“人民网发布”。 |
| `summary.py` | `generate_summary(news, keywords=None, max_length=120)` | 组合发布时间、来源、标题、正文首句和关键词，生成摘要。 |
| `sentiment.py` | `analyze_sentiment(text)` | 使用 `SnowNLP(text).sentiments` 得到情感分数，并转换为 `positive`、`neutral`、`negative` 三类比例。 |
| `sentiment.py` | `_normalize_distribution()` | 把正面、中性、负面三个值归一化到总和约等于 1。 |

### 7.4 相似新闻

`similarity.py` 的输出 `similar_news` 是给 1 号后端做事件聚合的辅助信号，不代表 4 号模块已经完成最终事件聚合。

| 函数 | 功能 | 变量含义 |
| --- | --- | --- |
| `find_similar_news(current_news, all_news, threshold=0.18, max_count=5)` | 返回相似新闻的 `news_id` 列表。 | 使用 `scikit-learn` 的 TF-IDF 和余弦相似度；缺少 `scikit-learn` 时抛出 `AnalysisDependencyError`。 |
| `_parse_time(value)` | 把发布时间字符串转成 `datetime`。 | 无法解析时返回 `None`。 |
| `_time_similarity(news_a, news_b)` | 根据发布时间差距给时间相似分。 | 6 小时内最高，24 小时内较高，72 小时内较低。 |
| `_source_similarity(news_a, news_b)` | 根据来源平台是否相同或包含关系给来源相似分。 | `source_a`、`source_b` 是标准化来源。 |
| `_url_domain(url)` | 提取链接域名。 | 用于判断两个新闻是否来自同一站点。 |
| `_url_similarity(news_a, news_b)` | 比较两个新闻链接域名是否一致。 | 域名一致返回 1，否则返回 0。 |
| `_combine_similarity(text_score, current_news, candidate)` | 把文本相似度和元数据相似度合成总分。 | 文本分太低时，不会因为时间或来源接近而强行判相似。 |

### 7.5 热度、风险、生命周期

当前热度计算已经不再只考虑负面情绪，而是把正面和负面情绪中的主导情绪作为情绪强度来源。

```text
similar_score = min(len(similar_news) * 25, 100)
keyword_score = min(sensitive_hits * 25, 100)
sentiment_score = min(max(positive, negative) * 100 + min(positive, negative) * 40, 100)

heat_score = similar_score * 0.45 + keyword_score * 0.25 + sentiment_score * 0.30
```

含义：

- `similar_score`：相似新闻数量得分，表示传播范围。
- `keyword_score`：敏感关键词命中得分，表示舆情敏感度。
- `sentiment_score`：情绪强度得分，强正面和强负面都可以提高热度。
- `risk_level`：风险等级仍重点参考负面情绪，因为热度和风险不是同一个概念。

| 文件 | 函数 | 说明 |
| --- | --- | --- |
| `heat_score.py` | `calculate_heat_score(keywords, sentiment, similar_news)` | 计算 0 到 100 的热度指数，综合相似新闻数量、敏感关键词和正负情绪强度。 |
| `heat_score.py` | `judge_risk_level(heat_score, sentiment)` | 根据热度和负面情绪返回风险等级，设计意图为低、中、高。 |
| `lifecycle.py` | `_related_news(current_news, all_news, similar_news)` | 找出当前新闻和 `similar_news` 对应的相关新闻集合。 |
| `lifecycle.py` | `_time_span_hours(news_items)` | 计算相关新闻最早发布时间到最晚发布时间的小时差。 |
| `lifecycle.py` | `_platform_count(news_items)` | 统计相关新闻覆盖了多少不同来源平台。 |
| `lifecycle.py` | `predict_lifecycle(current_news, all_news, heat_score, similar_news, previous_heat_score=None)` | 根据热度、相似新闻数量、传播平台数、时间跨度和历史热度判断潜伏期、成长期、高潮期、衰退期。 |

## 八、依赖检查和错误处理

analysis 模块现在必须安装以下第三方库：

```text
jieba
snownlp
scikit-learn
```

安装命令：

```powershell
python -m pip install jieba snownlp scikit-learn
```

验证命令：

```powershell
python -c "import jieba, snownlp, sklearn; print('ok')"
```

错误处理规则：

- 如果缺少 `jieba`、`SnowNLP` 或 `scikit-learn`，模块会抛出 `AnalysisDependencyError`。
- 缺依赖时不会返回半成品 JSON，也不会静默使用简单规则兜底。
- `demo.py` 和 `preprocess_demo.py` 会捕获该异常并输出清楚提示。
- 后端正式集成时也可以捕获 `AnalysisDependencyError`，向前端或控制台提示先安装依赖。

示例：

```python
from analysis import AnalysisDependencyError, analyze_news

try:
    result = analyze_news(news, all_news)
except AnalysisDependencyError as exc:
    # 后端可以在这里记录日志或返回友好错误信息
    print(f"analysis 依赖检查失败：{exc}")
```

## 九、小组对接说明

### 与 1 号后端

后端需要传入：

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

## 十、demo 文件说明

完整流程演示：

```powershell
python -m analysis.demo
```

预处理演示：

```powershell
python -m analysis.preprocess_demo
```

说明：

- `demo.py` 模拟多条新闻输入，测试完整 `analyze_news_batch()` 流程。
- `preprocess_demo.py` 只测试 `preprocess_news()`，适合展示清洗、字段标准化、分词和 `missing_fields` 的作用。
- 如果依赖未安装，demo 会提示缺少依赖并退出。

## 十一、当前注意事项

- 当前部分源码中的中文注释、示例新闻、词典词、风险等级和生命周期返回值曾存在编码乱码；如果展示时发现乱码，建议单独修复源码编码。
- `tokens` 和 `token_count` 是 `preprocess.py` 内部结果，供分词、关键词或调试使用，按当前对接要求不返回给 1 号后端。
- `lifecycle_prediction` 字段已经不再单独输出，生命周期预测统一使用 `stage` 字段。
- `previous_heat_score` 当前多数情况下会是 `None`，因为 4 号输入是新闻 `news`，不负责确定 `event_id`。
- `similar_news` 是辅助聚合信号，不等于最终 `event_id`，也不代表 4 号完成了事件合并。


重点强调：

- 输入不仅有标题和正文，还包括来源、发布时间和链接，这些字段会参与相似新闻和生命周期判断。
- `summary` 是返回给后端保存的摘要字段，5 号 AI 服务可以复用。
- `similar_news` 只是辅助后端聚合事件，不是最终聚合结果。
- 热度计算已经综合传播范围、敏感关键词和正负情绪强度，不再只看负面情绪。
- 依赖缺失时会明确抛错，不再静默走兜底方案，避免生成不可靠的分析结果。
