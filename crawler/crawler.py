"""
新闻采集模块
===========
使用 requests + BeautifulSoup(lxml) 从多个新闻网站采集原始文章数据。

职责边界：
  crawler.py = HTTP 请求 + HTML 解析 + 字段提取（不做清洗）
  cleaner.py = 文本清洗 + 日期解析 + 去重

输出统一字段：{title, content, source, url, publish_time}
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
        {title, content, publish_time, source, url}
        失败返回 None。
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

    return {
        "title": title,
        "content": content,
        "source": source["label"],
        "url": url,
        "publish_time": publish_time,
    }


# ============================================================
# 批量采集
# ============================================================

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
    known_urls = seen_urls if seen_urls is not None else set()

    # ================================================================
    # 第一遍：收集所有源的列表页链接（轮询混排，各源公平参与）
    # ================================================================
    source_urls: List[List[str]] = []
    for source in NEWS_SOURCES:
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

    logger.info(f"全部 {len(NEWS_SOURCES)} 个源，目标采集 {target} 篇")

    # ================================================================
    # 第二遍：遍历新链接，逐个采集
    # ================================================================
    articles: List[dict] = []
    total_skipped = 0

    for url in fresh_urls:
        if len(articles) >= target:
            break

        src = _find_source_for_url(url)
        article = fetch_article(url, src, session)
        if article:
            articles.append(article)
            logger.info(f"    [{len(articles)}/{target}] ✓ "
                        f"{article['title'][:40]} [{src['label']}]")
        else:
            total_skipped += 1
            # 失败的 URL 记入已知集合，后续轮次不再重试
            known_urls.add(url)

        time.sleep(REQUEST_DELAY)

    logger.info(f"采集完成: {len(articles)}/{target} 篇，"
                 f"共尝试 {len(articles) + total_skipped}，跳过 {total_skipped}")
    return articles


def _find_source_for_url(url: str) -> dict:
    """根据 URL 找到对应的新闻源配置"""
    for src in NEWS_SOURCES:
        if src["base_url"] in url or src["name"] in url:
            return src
    return NEWS_SOURCES[0]  # 兜底
