"""
新闻采集模块
===========
核心采集逻辑：支持人民网、新华网、中新网、新浪新闻、微博多源采集
新闻网站使用 requests + BeautifulSoup(lxml)，微博使用热搜API + crawl4weibo。

职责边界：
  crawler.py = HTTP 请求 + HTML 解析 + 字段提取（不做清洗）
  cleaner.py = 文本清洗 + 日期解析 + 去重

输出统一字段（15字段）：{title, content, source, url, publish_time, platform, author, account_id, account_name, account_type, is_official, crawl_time, repost_count, comment_count, like_count, reference_urls}
"""

import os
import time
import hashlib
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from crawler.config import (
    NEWS_SOURCES,
    MAX_ARTICLES_PER_RUN,
    REQUEST_TIMEOUT,
    REQUEST_DELAY,
)
from crawler.utils import (
    setup_logger,
    DEFAULT_HEADERS,
)

logger = setup_logger(__name__)

# ============================================================
# 文章 URL 过滤规则
# ============================================================

ARTICLE_URL_BLOCKLIST = [
    "video", "/tv/", "photo", "tupian", "live", "bbs",
    "/special/", "/zt/", "slide", "app.people", "dangjian",
    "www.people.com.cn",   # 主站文章几乎全404，只采各频道子域名
    "#liuyan",              # 锚点重复，已在列表页有原始链接
    # 新浪特有
    "lottery",              # 彩票频道
    "sports.sina.com.cn/l/",  # 体育专题/列表页，非文章
]


def _is_article_url(url: str) -> bool:
    """检查 URL 是否为文章页面"""
    url_lower = url.lower()
    for keyword in ARTICLE_URL_BLOCKLIST:
        if keyword in url_lower:
            return False
    return True


# ============================================================
# 调试
# ============================================================

DEBUG_DIR = "debug_html"


def _save_debug_html(filename: str, html: str):
    """保存 HTML 到调试目录"""
    os.makedirs(DEBUG_DIR, exist_ok=True)
    filepath = os.path.join(DEBUG_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"  调试 HTML 已保存: {filepath}")


# ============================================================
# 辅助函数
# ============================================================

def _safe_select(soup: BeautifulSoup, selector: str):
    """按选择器提取第一个匹配元素，支持逗号分隔的备选"""
    for sel in selector.split(","):
        sel = sel.strip()
        result = soup.select_one(sel)
        if result:
            return result
    return None


def _make_session() -> requests.Session:
    """创建带默认请求头的 Session"""
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    return session


# ============================================================
# 列表页采集
# ============================================================

def fetch_news_list(source: dict, session: requests.Session) -> List[str]:
    """
    从单个新闻源的列表页提取文章 URL。

    Args:
        source: NEWS_SOURCES 中的一条配置
        session: 复用的 requests.Session

    Returns:
        文章 URL 列表（去重后的绝对路径）
    """
    selectors = source["selectors"]
    article_path = source["article_path"]
    base_url = source["base_url"]
    urls: List[str] = []

    for list_url in source["list_urls"]:
        logger.info(f"  正在请求: {list_url}")

        try:
            resp = session.get(list_url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or source["encoding"]
        except requests.RequestException as e:
            logger.warning(f"  请求失败: {list_url} — {e}")
            continue

        soup = BeautifulSoup(resp.text, "lxml")
        channel_count = 0

        for link in soup.select(selectors["list_link"]):
            href = link.get("href")
            if not href:
                continue

            abs_url = urljoin(base_url, href)

            if not abs_url.startswith("http"):
                continue
            if abs_url in urls:
                continue
            if not _is_article_url(abs_url):
                continue
            if article_path not in abs_url:
                continue

            urls.append(abs_url)
            channel_count += 1

        if channel_count == 0:
            page_title = soup.title.get_text(strip=True) if soup.title else "无"
            logger.warning(f"  该频道 0 个链接（页面标题: {page_title}）")
        else:
            logger.info(f"  {list_url} → {channel_count} 个链接")

    return urls


# ============================================================
# 文章详情采集
# ============================================================

def fetch_article(url: str, source: dict, session: requests.Session) -> Optional[dict]:
    """
    抓取单篇文章的原始数据。

    Args:
        url: 文章 URL
        source: NEWS_SOURCES 中的一条配置
        session: 复用的 requests.Session

    Returns:
        完整15字段 dict，失败返回 None。
    """
    selectors = source["selectors"]

    logger.info(f"  正在抓取: {url}")

    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or source["encoding"]
    except requests.RequestException as e:
        logger.warning(f"  请求失败，跳过: {url} — {e}")
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    # --- 标题 ---
    title_el = _safe_select(soup, selectors["article_title"])
    title = title_el.get_text(strip=True) if title_el else ""
    if not title:
        for h in soup.find_all("h1"):
            t = h.get_text(strip=True)
            if t:
                title = t
                break
    if not title and soup.title:
        raw_title = soup.title.get_text(strip=True)
        title = raw_title.split("--")[0].split("-")[0].split("丨")[0].strip()
    if not title:
        logger.warning(f"  标题为空，跳过: {url}")
        return None

    # --- 正文（原始 HTML，由 cleaner 清洗）---
    content_el = _safe_select(soup, selectors["article_content"])
    if content_el:
        content = str(content_el)
    else:
        logger.warning(f"  未匹配正文容器，保存调试 HTML: {url}")
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        _save_debug_html(f"{source['name']}_{url_hash}.html", resp.text)
        body = soup.find("body")
        content = str(body) if body else ""

    # --- 发布时间（原始文本，由 cleaner 解析）---
    time_el = _safe_select(soup, selectors["article_time"])
    if time_el:
        if time_el.name == "meta":
            publish_time = time_el.get("content", "")
        else:
            publish_time = time_el.get_text(strip=True)
    else:
        publish_time = ""

    crawl_time = time.strftime("%Y-%m-%d %H:%M:%S")

    # 尝试提取作者/来源
    author = ""
    author_sel = selectors.get("article_author", "")
    if author_sel:
        author_el = _safe_select(soup, author_sel)
        if author_el:
            author = author_el.get_text(strip=True)

    # 判断是否官媒（人民网、新华网、中新网为官方媒体）
    is_official = source.get("is_official", source["name"] in ("people", "xinhua", "chinanews"))

    return {
        "title": title,
        "content": content,
        "source": source["label"],
        "url": url,
        "publish_time": publish_time,
        "platform": "新闻网站",
        "author": author,
        "account_id": "",
        "account_name": "",
        "account_type": "媒体",
        "is_official": is_official,
        "crawl_time": crawl_time,
        "repost_count": 0,
        "comment_count": 0,
        "like_count": 0,
        "reference_urls": [],
    }


# ============================================================
# 批量采集
# ============================================================

# ============================================================
# 微博热搜采集
# ============================================================

def _fetch_weibo_posts(source: dict) -> List[dict]:
    """
    微博热搜采集流程：
      1. 调用热搜 API 获取实时热搜榜
      2. 对每个热搜词搜索相关帖子
      3. 返回统一15字段格式

    Args:
        source: type="weibo" 的配置项

    Returns:
        原始文章 dict 列表（15字段，content 已是纯文本）
    """
    from crawl4weibo import WeiboClient

    client = WeiboClient()
    session = client.session

    topics_per = source.get("topics_per_run", 10)
    posts_per = source.get("posts_per_topic", 3)
    articles: List[dict] = []

    # ---- Step 1: 获取实时热搜榜 ----
    logger.info(f"  正在获取微博热搜榜...")
    try:
        resp = session.get(
            source["hot_search_url"],
            timeout=REQUEST_TIMEOUT,
            headers={
                "Referer": "https://weibo.com/",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"  微博热搜获取失败: {e}")
        return []

    realtime = data.get("data", {}).get("realtime", [])
    topics = realtime[:topics_per]
    logger.info(f"  热搜榜获取成功: {len(topics)} 个热搜词")

    # ---- Step 2: 逐热搜词搜索帖子 ----
    crawl_time = time.strftime("%Y-%m-%d %H:%M:%S")
    user_cache = {}  # 缓存用户信息，避免重复查询

    for rank, topic in enumerate(topics, 1):
        word = topic.get("word", "")
        if not word:
            continue

        logger.info(f"  [{rank}/{len(topics)}] 搜索帖子: {word[:30]}")
        try:
            results = client.search_posts(word, page=1)
            if not results or not results[0]:
                continue

            # 按正文长度排序，优先取内容较丰富的帖子
            sorted_posts = sorted(results[0], key=lambda p: len(p.text or ""), reverse=True)
            for post in sorted_posts[:posts_per]:
                # 长文本展开：搜索API对 >140字 的帖子返回截断文本（末尾"全文"），
                # 需通过 get_post_by_bid 获取完整内容。
                if post.is_long_text:
                    try:
                        full_post = client.get_post_by_bid(post.bid)
                        post.text = full_post.text
                    except Exception as e:
                        logger.warning(f"    展开长帖失败 {post.bid}: {e}")
                text = post.text.strip()
                # 微博无标题，取正文第一行作为标题，尽量截断到完整句子末尾
                first_line = text.split("\n")[0]
                if len(first_line) <= 80:
                    title = first_line
                else:
                    segment = first_line[:80]
                    cut = -1
                    for p in ("。", "！", "？", "…", "~"):
                        p_idx = segment.rfind(p)
                        if p_idx > cut:
                            cut = p_idx
                    title = segment[:cut + 1] if cut > 20 else segment

                raw_time = str(post.created_at) if post.created_at else ""
                if "+" in raw_time:
                    raw_time = raw_time.split("+")[0]

                # --- 查用户认证信息 ---
                author = ""
                account_name = ""
                account_type = "普通用户"
                is_official = False

                uid = str(post.user_id) if post.user_id else ""
                if uid and uid not in user_cache:
                    try:
                        user = client.get_user_by_uid(uid)
                        user_cache[uid] = user
                    except Exception:
                        user_cache[uid] = None
                user = user_cache.get(uid)

                if user:
                    author = user.screen_name or ""
                    account_name = user.screen_name or ""
                    verified_reason = str(user.verified_reason or "")
                    if user.verified:
                        if any(kw in verified_reason for kw in
                               ["媒体", "新闻", "报社", "新闻网", "TV", "广播", "记者", "日报", "周刊"]):
                            account_type = "媒体"
                        elif any(kw in verified_reason for kw in
                                 ["政府", "公安", "法院", "检察院", "官方", "中国", "国家",
                                  "部", "委", "局", "办", "发布", "消防", "军队", "大使馆"]):
                            account_type = "官方机构"
                        else:
                            account_type = "大V"
                    is_official = account_type in ("媒体", "官方机构")

                articles.append({
                    "title": title,
                    "content": text,
                    "source": source["label"],
                    "url": f"https://weibo.com/{post.user_id}/{post.bid}",
                    "publish_time": raw_time,
                    "platform": "微博",
                    "author": author,
                    "account_id": uid,
                    "account_name": account_name,
                    "account_type": account_type,
                    "is_official": is_official,
                    "crawl_time": crawl_time,
                    "repost_count": post.reposts_count or 0,
                    "comment_count": post.comments_count or 0,
                    "like_count": post.attitudes_count or 0,
                    "reference_urls": [],
                })
        except Exception as e:
            logger.warning(f"    搜索 '{word}' 失败: {e}")
            continue

        time.sleep(1.0)

    return articles


def fetch_all_news(max_articles: Optional[int] = None,
                   seen_urls: set = None) -> List[dict]:
    """
    先收集所有新闻源的全部链接，再逐个采集直到凑够目标数量。
    下载前检查 URL 是否已见过，避免重复请求。

    Args:
        max_articles: 目标篇数，None 使用配置默认值。
        seen_urls: 已采集 URL 集合（下载前过滤），None 则不检查。

    Returns:
        原始文章 dict 列表
    """
    target = max_articles if max_articles is not None else MAX_ARTICLES_PER_RUN
    session = _make_session()
    known_urls = set(seen_urls) if seen_urls is not None else set()

    # 分离新闻源和微博
    news_sources = [s for s in NEWS_SOURCES if s.get("type") != "weibo"]
    weibo_sources = [s for s in NEWS_SOURCES if s.get("type") == "weibo"]

    articles: List[dict] = []

    # ================================================================
    # 微博：热搜 → 搜索 → 帖子（先执行，不占新闻配额）
    # ================================================================
    weibo_count = 0
    for src in weibo_sources:
        logger.info(f"微博热搜采集: {src['label']}")
        weibo_posts = _fetch_weibo_posts(src)
        # 过滤已采集
        fresh = []
        for a in weibo_posts:
            if a["url"] not in known_urls:
                fresh.append(a)
                known_urls.add(a["url"])
        articles.extend(fresh)
        weibo_count += len(fresh)
        logger.info(f"  {src['label']} → {len(fresh)} 条新帖子")

    # ================================================================
    # 第一遍：收集所有新闻源的列表页链接（轮询混排，各源公平参与）
    # ================================================================
    source_urls: List[List[str]] = []
    for source in news_sources:
        logger.info(f"扫描列表页: {source['label']}")
        urls = fetch_news_list(source, session)
        logger.info(f"  {source['label']} → {len(urls)} 个链接")
        source_urls.append(urls)

    # 轮询混排：从每个源轮流取一个URL
    all_urls: List[str] = []
    max_len = max(len(u) for u in source_urls) if source_urls else 0
    for i in range(max_len):
        for urls in source_urls:
            if i < len(urls):
                all_urls.append(urls[i])

    # 排除已采集URL，避免重复下载
    fresh_urls = [u for u in all_urls if u not in known_urls]
    skipped_known = len(all_urls) - len(fresh_urls)
    if skipped_known:
        logger.info(f"跳过已采集 {skipped_known} 个链接，剩余 {len(fresh_urls)} 个新链接")

    logger.info(f"全部 {len(news_sources)} 个新闻源 + {len(weibo_sources)} 个社交源，"
                 f"新闻目标 {target} 篇")

    # ================================================================
    # 第二遍：遍历新链接，逐个采集（新闻源，不含微博已采部分）
    # ================================================================
    total_skipped = 0

    for url in fresh_urls:
        if len(articles) - weibo_count >= target:
            break

        src = _find_source_for_url(url)
        article = fetch_article(url, src, session)
        if article:
            articles.append(article)
            logger.info(f"    [{len(articles) - weibo_count}/{target}] ✓ "
                        f"{article['title'][:40]} [{src['label']}]")
        else:
            total_skipped += 1
            # 失败的 URL 记入已知集合，后续轮次不再重试
            known_urls.add(url)

        time.sleep(REQUEST_DELAY)

    news_count = len(articles) - weibo_count
    logger.info(f"采集完成: 新闻 {news_count}/{target} 篇 + 微博 {weibo_count} 篇 = {len(articles)} 篇，"
                 f"跳过 {total_skipped}")
    return articles


def _find_source_for_url(url: str) -> dict:
    """根据 URL 找到对应的新闻源配置（仅新闻类型源）"""
    from urllib.parse import urlparse

    url_domain = urlparse(url).netloc.lower()

    for src in NEWS_SOURCES:
        if src.get("type") == "weibo":
            continue
        src_domain = urlparse(src.get("base_url", "")).netloc.lower()
        # 用域名匹配（忽略协议差异），或用 source name 兜底
        if (src_domain and src_domain in url_domain) or src["name"] in url:
            return src

    # 兜底：返回第一个新闻源
    for src in NEWS_SOURCES:
        if src.get("type") != "weibo":
            return src
    return NEWS_SOURCES[0]
