# Crawler 模块开发文档

## 模块概述

网络舆情事件智能分析系统的数据采集层，覆盖 5 个数据源（人民网、新华网、中新网、新浪新闻、微博），自动采集、清洗去重、输出统一 JSON 供后端和 NLP 分析使用。


## 技术栈

- **requests** — HTTP 请求
- **BeautifulSoup** (lxml) — HTML 解析
- **crawl4weibo** — 微博热搜采集 + 用户认证查询
- **json / hashlib** — 数据输出与去重

## 目录结构

```
crawler/
├── __init__.py         # 包入口，导出 run_once()
├── config.py           # 新闻源配置、CSS选择器、采集参数、输出路径
├── crawler.py          # 多源采集（HTTP请求、HTML解析、字段提取）
├── cleaner.py          # 文本清洗 + URL 去重 + 质量过滤
├── pipeline.py         # 管道编排（采集→清洗→去重→输出JSON）
├── run.py              # 命令行入口（单次/持续/限制篇数）
├── utils.py             # 工具函数（日志/时间解析/请求头）
├── requirements.txt    # Python 依赖清单
└── README.md           # 本开发文档
```

## 数据流

```
新闻网站（4源16频道）                     微博（1源40热搜词，每词1条帖子）
    │                                        │
    ├─ 人民网（7频道）                       ├─ 热搜API → 热搜榜TOP40
    ├─ 新华网（3频道）                       ├─ 逐词搜索帖子（每词1条）
    ├─ 中新网（2频道）                       └─ 查询用户认证信息（大V/官媒/普通）
    └─ 新浪新闻（4频道）                         │
    │                                        ▼
    ▼                                   产生约40条原始数据
列表页提取链接 → 路径过滤 → 约1100个链接
    │
    ▼
下载前URL查重（跳过已采集和失败的）
    │
    ▼
逐个下载 → 提取标题/正文/时间/作者 → 原始数据
    │
    ▼
文本清洗（去HTML/去噪声/去版权尾）
    │
    ▼
URL去重（同URL不重复采集）
    │
    ▼
质量过滤（标题非空/时间非空/新闻≥50字 微博≥30字/非专题页）
    │
    ▼
15字段统一输出 → output/YYYY-MM-DD.json
```

## 统一输出格式（15字段）

```json
{
    "title": "新闻标题",
    "content": "新闻正文纯文本",
    "source": "人民网",
    "url": "http://finance.people.com.cn/n1/...",
    "publish_time": "2026-07-08 10:00:00",
    "platform": "新闻网站",
    "author": "作者或账号名称",
    "account_id": "",
    "account_name": "",
    "account_type": "媒体",
    "is_official": true,
    "crawl_time": "2026-07-08 10:05:00",
    "repost_count": 0,
    "comment_count": 0,
    "like_count": 0,
    "reference_urls": []
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| title | string | 新闻标题/首行文字 |
| content | string | 正文纯文本 |
| source | string | 来源（人民网/新华网/中新网/新浪新闻/微博）|
| url | string | 原文链接 |
| publish_time | string | 发布时间 YYYY-MM-DD HH:mm:ss |
| platform | string | 新闻网站 / 微博 |
| author | string | 作者或发布账号 |
| account_id | string | 平台账号ID |
| account_name | string | 平台账号名称 |
| account_type | string | 媒体 / 官方机构 / 大V / 普通用户 |
| is_official | bool | 是否官媒或权威来源 |
| crawl_time | string | 采集时间 |
| repost_count | number | 转发量（新闻为0） |
| comment_count | number | 评论量（新闻为0） |
| like_count | number | 点赞量（新闻为0） |
| reference_urls | array | 正文引用链接 |

## 使用方式

```bash
# 安装依赖
pip install -r crawler/requirements.txt

# 单次采集（默认新闻120篇 + 微博约40篇 = 约160篇）
python -m crawler.run

# 限制新闻篇数
python -m crawler.run --max 50

# 持续采集（每10分钟一轮）
python -m crawler.run --loop 10
```
## 数据源配置

添加新源只需在 `config.py` 的 `NEWS_SOURCES` 列表中新增一条：

**新闻网站**（列表页→文章页模式）：
```python
{
    "name": "标识",
    "label": "显示名称",
    "base_url": "https://www.example.com",
    "encoding": "utf-8",
    "article_path": "/2026/",
    "list_urls": ["https://www.example.com/news/"],
    "selectors": {
        "list_link": "a[href]",
        "article_title": "h1",
        "article_content": "div.content",
        "article_time": "span.time",
    },
}
```

**社交平台**（热搜→搜索模式）：
```python
{
    "type": "weibo",
    "name": "weibo",
    "label": "微博",
    "hot_search_url": "https://weibo.com/ajax/side/hotSearch",
    "topics_per_run": 40,        # 取前N个热搜词
    "posts_per_topic": 1,        # 每词采几条帖子
}
```

## 核心设计

### URL 去重

- 同 URL 不重复采集
- 失败 URL 自动记入去重库，后续轮次不再浪费请求
- 微博热搜每轮产生新 URL，不受历史去重影响

### 质量过滤

- 标题非空
- 发布时间非空（解析失败则丢弃）
- 正文最短：新闻 ≥ 50 字符，微博 ≥ 30 字符
- 微博帖子按长度排序，优先取内容最丰富的
- "更多+" 出现 ≤ 3 次（过滤专题列表页）
- 自动截断版权尾部（"人民网股份有限公司"、"Copyright ©"）

### 容错设计

- 单篇文章失败 → 跳过继续下一篇
- 单个频道失败 → 跳过继续下一频道
- 列表页 0 链接 → 打印页面标题和前 5 个链接辅助调试
- 正文容器未命中 → 保存 HTML 到 debug_html/