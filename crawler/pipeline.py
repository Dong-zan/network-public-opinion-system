"""
数据管道模块
===========
串联 采集 → 清洗 → 去重 → 输出JSON 全流程。

用法：
    from crawler.pipeline import run_once, save_articles
    articles = run_once()                        # 真实采集
    articles = run_once(max_articles=50)          # 限制篇数
    count = save_articles(articles)              # 仅保存 JSON
"""

import json
import os
import hashlib
from datetime import datetime
from typing import List, Optional

from crawler.config import OUTPUT_DIR, MAX_ARTICLES_PER_RUN
from crawler.utils import setup_logger
from crawler.crawler import fetch_all_news
from crawler.cleaner import clean_and_dedup, Deduplicator
logger = setup_logger(__name__)


# ============================================================
# 辅助：内容哈希
# ============================================================

def _content_hash(title: str, content: str) -> str:
    """计算 标题 + 正文 的 MD5，降低仅开头相似的误判"""
    hash_text = f"{title}|{content}"
    return hashlib.md5(hash_text.encode("utf-8")).hexdigest()


# ============================================================
# JSON 输出（私有函数，由 save_articles 调用）
# ============================================================

def _save_to_json(articles: List[dict], output_dir: str = None) -> int:
    """
    将文章保存到当天的 JSON 文件。

    同一天多次运行会合并到同一文件。
    合并去重：URL 相同 OR 标题+正文哈希相同 → 视为重复，不重复写入。

    Args:
        articles: 清洗后的文章列表
        output_dir: 输出目录，默认使用 config.OUTPUT_DIR

    Returns:
        实际新增写入的条数
    """
    directory = output_dir or OUTPUT_DIR
    os.makedirs(directory, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    filepath = os.path.join(directory, f"{today}.json")

    # 读取已有数据
    existing: List[dict] = []
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            existing = []

    # 构建已有数据索引：URL + 内容哈希
    existing_urls = {item.get("url", "") for item in existing}
    existing_hashes = {
        _content_hash(item.get("title", ""), item.get("content", ""))
        for item in existing
        if item.get("content")
    }

    # 过滤：URL 或内容哈希匹配的都算重复
    new_items: List[dict] = []
    for a in articles:
        url = a.get("url", "")
        h = _content_hash(a.get("title", ""), a.get("content", ""))
        if url and url in existing_urls:
            continue
        if h and h in existing_hashes:
            continue
        new_items.append(a)

    if new_items:
        merged = existing + new_items
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        logger.info(f"已写入 {filepath}（新增 {len(new_items)} 篇，累计 {len(merged)} 篇）")
    else:
        logger.info(f"无新数据写入 {filepath}")

    return len(new_items)


# ============================================================
# 公开 API
# ============================================================

def save_articles(articles: List[dict], output_dir: str = None) -> int:
    """
    将清洗后的文章保存到 JSON 文件（公开接口）。

    Args:
        articles: 清洗后的文章列表
        output_dir: 输出目录，默认使用 config.OUTPUT_DIR

    Returns:
        实际写入条数
    """
    return _save_to_json(articles, output_dir)


def run_once(
    max_articles: Optional[int] = None,
) -> List[dict]:
    """
    执行一次完整的 采集→清洗→去重→输出 管道。

    Args:
        max_articles: 最多采集篇数，None 使用配置默认值

    Returns:
        清洗后的文章列表，每条 5 个字段:
        {title, content, publish_time, source, url}
    """
    limit = max_articles if max_articles is not None else MAX_ARTICLES_PER_RUN

    # ================================================================
    # Step 1: 采集
    # ================================================================
    logger.info("=" * 50)
    logger.info("管道启动：开始采集新闻")

    # 提前加载去重状态，让爬虫下载前就能过滤已知URL
    dedup = Deduplicator()

    raw_articles = fetch_all_news(limit, seen_urls=dedup.seen_urls)
    if not raw_articles:
        logger.warning("真实采集返回 0 条，请检查网络或新闻源配置")

    logger.info(f"采集到 {len(raw_articles)} 条原始数据")

    # ================================================================
    # Step 2: 清洗 + 去重
    # ================================================================
    logger.info("-" * 50)
    logger.info("开始清洗与去重")

    articles = clean_and_dedup(raw_articles, dedup)

    # ================================================================
    # Step 3: 输出 JSON + 持久化去重
    # ================================================================
    logger.info("-" * 50)
    logger.info("开始输出 JSON")

    try:
        if articles:
            written = save_articles(articles)
            logger.info(f"JSON 输出完成：写入 {written} 篇新文章")
        else:
            logger.info("无新文章可写入（全部重复或为空）")
    finally:
        dedup.save()
        logger.info(f"去重状态: {dedup.stats()}")

    logger.info("=" * 50)
    return articles
