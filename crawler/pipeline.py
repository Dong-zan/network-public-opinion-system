"""
数据管道模块
===========
串联 采集 → 清洗 → 去重 → 输出JSON → 推送后端 全流程。

用法：
    from crawler.pipeline import run_once, save_articles
    articles = run_once()                        # 真实采集
    articles = run_once(max_articles=50)         # 限制篇数
    count = save_articles(articles)              # 仅保存 JSON
"""

import json
import os
from datetime import datetime
from typing import List, Optional

import requests

from crawler.config import OUTPUT_DIR, MAX_ARTICLES_PER_RUN, BACKEND_URL
from crawler.utils import normalize_publish_time, setup_logger
from crawler.crawler import fetch_all_news
from crawler.cleaner import clean_and_dedup, Deduplicator
logger = setup_logger(__name__)


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

    # 已有数据索引：URL
    existing_urls = {item.get("url", "") for item in existing}

    # 过滤：URL 相同则跳过
    new_items: List[dict] = []
    for a in articles:
        url = a.get("url", "")
        if url and url in existing_urls:
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


def _upload_to_backend(
    articles: List[dict],
    backend_url: str = None,
) -> int:
    """
    推送新文章到后端 API。

    Returns:
        成功推送的条数
    """
    target_url = backend_url or BACKEND_URL
    if not target_url or not articles:
        return 0

    success_count = 0
    for index, article in enumerate(articles):
        payload = dict(article)
        payload["publish_time"] = normalize_publish_time(
            payload.get("publish_time")
        )
        try:
            resp = requests.post(
                target_url,
                json=[payload],
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            if resp.status_code != 200:
                logger.warning(
                    "单篇文章推送失败 index=%s url=%r status=%s response=%s",
                    index,
                    payload.get("url"),
                    resp.status_code,
                    resp.text[:200],
                )
                continue

            response_data = resp.json().get("data", {})
            if not response_data.get("news_ids"):
                logger.warning(
                    "单篇文章未入库 index=%s url=%r response=%s",
                    index,
                    payload.get("url"),
                    resp.text[:200],
                )
                continue
            success_count += 1
        except Exception as exc:
            logger.warning(
                "单篇文章推送异常，继续下一篇 index=%s url=%r error=%s",
                index,
                payload.get("url"),
                exc,
            )

    logger.info(
        "后端推送完成: 成功 %s 篇，失败 %s 篇",
        success_count,
        len(articles) - success_count,
    )
    return success_count


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

    # ================================================================
    # Step 4: 推送到后端
    # ================================================================
    if articles:
        logger.info("-" * 50)
        logger.info("推送后端")
        _upload_to_backend(articles)

    logger.info("=" * 50)
    return articles
