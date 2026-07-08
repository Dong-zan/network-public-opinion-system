# Crawler 模块开发文档

## 模块概述

网络舆情事件智能分析系统的数据采集层，负责从多个主流新闻网站自动采集新闻、清洗去重、输出统一 JSON 格式供后端和 NLP 分析使用。

## 技术栈

- **requests** — HTTP 请求
- **BeautifulSoup** (lxml) — HTML 解析
- **json / hashlib** — 数据输出与去重

## 目录结构

```
crawler/
├── __init__.py         # 包入口，导出 run_once()
├── config.py           # 新闻源配置、CSS选择器、采集参数、输出路径
├── crawler.py          # 多源采集（HTTP请求、HTML解析、字段提取）
├── cleaner.py          # 文本清洗 + 双层去重（URL + 内容哈希）+ 质量过滤
├── pipeline.py         # 管道编排（采集→清洗→去重→输出JSON）
├── run.py              # 命令行入口（单次/持续/限制篇数）
├── requirements.txt    # Python 依赖清单
└── README.md           # 本开发文档
```

## 数据流

```
列表页扫描（12个频道）
    │
    ├─ 人民网：财经/科技/文化/社会/教育/健康/国际（7个频道）
    ├─ 新华网：时政/地方/财经（3个频道）
    └─ 中新网：首页/滚动（2个频道）
    │
    ▼
提取文章链接 → 过滤 /n1//c.html/.shtml 路径 → 约450个有效链接
    │
    ▼
下载前查重（跳过已采集和失败的URL）
    │
    ▼
逐个下载文章 → 提取 标题/正文/时间 → 原始数据
    │
    ▼
文本清洗（去HTML/去噪声/去版权尾）
    │
    ▼
双层去重（URL匹配 OR 标题+正文MD5匹配）
    │
    ▼
质量过滤（标题非空/时间非空/正文≥50字/非专题页）
    │
    ▼
输出 output/YYYY-MM-DD.json
```

## 统一输出格式

```json
{
    "title": "新闻标题",
    "content": "新闻正文纯文本",
    "source": "人民网",
    "url": "http://finance.people.com.cn/n1/...",
    "publish_time": "2026-07-08 10:00:00"
}
```

## 使用方式

```bash
# 安装依赖
pip install -r crawler/requirements.txt

# 单次采集（默认100篇）
python -m crawler.run

# 限制篇数
python -m crawler.run --max 50

# 持续采集（每10分钟一轮）
python -m crawler.run --loop 10
```

## 后端集成

```python
from crawler import run_once
articles = run_once()  # → list[dict]，每条5个字段
```

## 新闻源配置

添加新源只需在 `config.py` 的 `NEWS_SOURCES` 列表中新增一条：

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

## 核心设计

### 双层去重

- **URL 去重**：同 URL 不重复下载
- **内容哈希去重**：标题+正文 MD5，跨站转载检测
- **下载前过滤**：失败 URL 自动记入去重库，后续轮次不再浪费请求

### 质量过滤

- 标题非空
- 发布时间非空（解析失败则丢弃）
- 正文 ≥ 50 字符
- "更多+" 出现 ≤ 3 次（过滤专题列表页）
- 自动截断版权尾部（"人民网股份有限公司"、"Copyright ©"）

### 容错设计

- 单篇文章失败 → 跳过继续下一篇
- 单个频道失败 → 跳过继续下一频道
- 列表页 0 链接 → 打印页面标题和前 5 个链接辅助调试
- 正文容器未命中 → 保存 HTML 到 debug_html/

## 开发历程

| 阶段 | 内容 |
|---|---|
| MVP | 单源（人民网社会频道），requests+BS4 采集+清洗+去重 |
| 增强 | 多频道聚合，质量过滤，版权截断，正文噪声清理 |
| 多源 | 新增新华网，per-source 选择器配置 |
| 实时 | --loop 持续模式，下载前去重，失败URL记忆 |
| 交付 | 统一5字段输出，清除模拟数据，后端可直接集成 |
