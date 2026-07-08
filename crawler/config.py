"""
Crawler 模块配置
===============
所有可调参数集中管理。新增新闻源只需在 NEWS_SOURCES 中添加一条。
"""

# ===========================================================
# 新闻源列表（每个源独立配置）
# ===========================================================

NEWS_SOURCES = [
    {
        "name": "people",                   # 内部标识
        "label": "人民网",                   # 显示名称
        "base_url": "http://www.people.com.cn",
        "encoding": "utf-8",
        "article_path": "/n1/",             # URL 中必须包含此路径才算文章
        "list_urls": [
            "http://finance.people.com.cn/",
            "http://scitech.people.com.cn/",
            "http://culture.people.com.cn/",
            "http://society.people.com.cn/",
            "http://edu.people.com.cn/",
            "http://health.people.com.cn/",
            "http://world.people.com.cn/",
        ],
        "selectors": {
            "list_link": "div.hdNews a, .news-list a, ul.list16 li a, ul li a[href]",
            "article_title": "h1",
            "article_content": "div.rm_txt_con, div.rm_txt, div.show_text, div.text_con, div.article, article",
            "article_time": "div.channel, div.time, span.date, div.channelTime, div.article-time, meta[name=\"publishdate\"]",
        },
    },
    {
        "name": "xinhua",                   # 内部标识
        "label": "新华网",                   # 显示名称
        "base_url": "https://www.news.cn",
        "encoding": "utf-8",
        "article_path": "/c.html",          # 新华网文章路径特征
        "list_urls": [
            "http://www.news.cn/politics/",
            "http://www.news.cn/local/",
            "http://www.news.cn/fortune/",
        ],
        "selectors": {
            "list_link": "a[href*='/c.html'], a[href*='/2026']",
            "article_title": "h1",
            "article_content": "p",         # 新华网正文分散在 <p> 标签中
            "article_time": "div.info, meta[name=\"date\"]",
        },
    },
    {
        "name": "chinanews",                # 内部标识
        "label": "中新网",                   # 显示名称
        "base_url": "https://www.chinanews.com.cn",
        "encoding": "utf-8",
        "article_path": ".shtml",           # 中新网文章路径特征
        "list_urls": [
            "https://www.chinanews.com.cn/",
            "https://www.chinanews.com.cn/scroll/",
        ],
        "selectors": {
            "list_link": "a[href*='/2026']",
            "article_title": "h1",
            "article_content": "div.left_zw, div.content",
            "article_time": "div.content_left_time",
        },
    },
]

# ============================================================
# 采集参数
# ============================================================

# 每次运行最多采集的文章数
MAX_ARTICLES_PER_RUN = 100

# HTTP 请求超时（秒）
REQUEST_TIMEOUT = 15

# 请求间隔（秒），避免对目标服务器造成压力
REQUEST_DELAY = 1.0

# ============================================================
# 输出配置
# ============================================================

# JSON 输出目录（相对于项目根目录）
OUTPUT_DIR = "output"

# ============================================================
# 去重配置
# ============================================================

# 去重记录文件路径
DEDUP_FILE = "data/seen_urls.json"

# 内容哈希：取正文前 N 个字符计算 MD5，用于跨站转载去重
CONTENT_HASH_PREFIX_LEN = 200

# ============================================================
# 日志配置
# ============================================================

LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
