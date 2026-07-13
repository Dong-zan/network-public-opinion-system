"""
数据清洗与去重模块
================
负责将 crawler.py 输出的原始数据清洗为标准化格式，并去除重复文章。

清洗流程：
  原始 HTML content ──► BeautifulSoup.get_text() ──► 去空白 ──► 去噪声行 ──► 纯文本
  原始 publish_time  ──► parse_datetime() ──► YYYY-MM-DD HH:MM:SS

去重逻辑：
  URL 精确匹配 → 判为重复（不再使用内容哈希，保留不同来源的相似内容）
"""

import html
import json
import os
import re
import hashlib
from typing import List, Set
from bs4 import BeautifulSoup

from crawler.config import DEDUP_FILE
from crawler.utils import (
    setup_logger,
    parse_datetime,
    remove_noise_lines,
)

logger = setup_logger(__name__)


# ===========================================================
# 文本清洗
# ===========================================================

def clean_html(html: str) -> str:
    """
    将原始 HTML 转为纯文本。

    处理步骤：
      1. BeautifulSoup(lxml) 解析
      2. 去除 <script> <style> <noscript> <iframe> 标签
      3. get_text() 提取文本，段落间用换行分隔
    """
    soup = BeautifulSoup(html, "lxml")

    # 移除不需要的标签
    for tag in soup.find_all(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    return text


def clean_text(text: str) -> str:
    """
    规范化纯文本：
      1. 合并连续空白行（3个以上换行 → 2个换行）
      2. 去除"责任编辑""本文来源"等噪声行
      3. 去除首尾空白
    """
    # 合并连续空白行
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 去除噪声行
    text = remove_noise_lines(text)

    # 去除首尾空白
    text = text.strip()

    return text


def clean_article(article: dict) -> dict | None:
    """
    清洗单篇文章的 content 和 publish_time 字段。

    返回 None 表示文章不合规，应丢弃。

    Args:
        article: crawler 输出的原始 dict（15字段）

    Returns:
        清洗后的 dict（15字段透传），或 None（文章无效）。
    """
    # --- 清洗正文 ---
    raw_content = article.get("content", "")
    # 如果是 HTML（包含标签），先提取纯文本
    if "<" in raw_content and ">" in raw_content:
        text = clean_html(raw_content)
    else:
        text = raw_content

    # 截断：遇到版权尾部直接删除后面所有内容
    text = _truncate_copyright(text)

    text = clean_text(text)

    # --- 清洗发布时间 ---
    publish_time = article.get("publish_time", "")

    # 如果上游 crawler 没有解析，则尝试解析为标准格式
    if publish_time:
        parsed_time = parse_datetime(publish_time)
        if parsed_time:
            publish_time = parsed_time

    title = article.get("title", "")

    # ================================================================
    # 质量过滤
    # ================================================================

    # 规则 1: 标题不能为空
    if not title.strip():
        return None

    # 规则 2: publish_time 不能为空
    if not publish_time:
        return None

    # 规则 3: 正文不能太短
    # 微博阈值 30 字（过滤纯表情/无意义帖）；新闻网站至少 50 字
    min_len = 30 if article.get("source") == "微博" else 50
    if len(text.strip()) < min_len:
        return None

    # 规则 4: 过滤专题/栏目页（"更多+" 出现超过 3 次说明是列表页）
    if text.count("更多+") > 3:
        return None

    # HTML 实体解码：用户可见文本字段，防止 &amp; &lt; &gt; &quot; 等原样入库
    return {
        "title": html.unescape(title),
        "content": html.unescape(text),
        "source": article.get("source", ""),
        "url": article.get("url", ""),
        "publish_time": publish_time,
        "platform": article.get("platform", ""),
        "author": html.unescape(article.get("author", "")),
        "account_id": article.get("account_id", ""),
        "account_name": html.unescape(article.get("account_name", "")),
        "account_type": article.get("account_type", ""),
        "is_official": article.get("is_official", False),
        "crawl_time": article.get("crawl_time", ""),
        "repost_count": article.get("repost_count", 0),
        "comment_count": article.get("comment_count", 0),
        "like_count": article.get("like_count", 0),
        "reference_urls": article.get("reference_urls", []),
    }


def _truncate_copyright(text: str) -> str:
    """遇到人民网版权声明则截断，删除后面的页脚"""
    markers = [
        "人 民 网 股 份 有 限 公 司",
        "Copyright ©",
    ]
    for marker in markers:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
    return text


# ============================================================
# 去重器
# ============================================================

class Deduplicator:
    """
    URL 去重器：记录已采集的 URL，避免重复下载。

    使用方式：
        dedup = Deduplicator()
        if url not in dedup.seen_urls:
            dedup.mark_seen(url)
            # 保存这篇
        dedup.save()  # 结束时持久化
    """

    def __init__(self, state_file: str = None):
        self.state_file = state_file or DEDUP_FILE
        self.seen_urls: Set[str] = set()
        self._load()

    # --- 哈希计算 ---

    @staticmethod
    def _compute_hash(title: str, content: str) -> str:
        """计算标题 + 正文的 MD5，降低仅开头相似的误判"""
        hash_text = f"{title}|{content}"
        return hashlib.md5(hash_text.encode("utf-8")).hexdigest()

    # --- 去重判断 ---

    def is_duplicate(self, url: str, title: str = "", content: str = "") -> bool:
        """
        判断文章是否重复。

        重复条件（满足任一）：
          1. URL 曾经出现过
          2. 标题 + 正文的 MD5 曾经出现过（跨站转载检测）

        Args:
            url: 文章 URL
            title: 文章标题
            content: 清洗后的纯文本正文
        """
        if url in self.seen_urls:
            return True
        if content:
            h = self._compute_hash(title, content)
            if h in self.seen_hashes:
                return True
        return False

    # --- 记录 ---

    def mark_seen(self, url: str, title: str = "", content: str = ""):
        """记录一篇文章为已见"""
        self.seen_urls.add(url)
        if content:
            h = self._compute_hash(title, content)
            self.seen_hashes.add(h)

    # --- 持久化 ---

    def save(self):
        """保存去重状态到 JSON 文件"""
        dir_name = os.path.dirname(self.state_file)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        data = {
            "seen_urls": list(self.seen_urls),
            "seen_hashes": list(self.seen_hashes),
        }
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug(f"去重状态已保存: {len(self.seen_urls)} URLs, "
                     f"{len(self.seen_hashes)} hashes")

    def _load(self):
        """从 JSON 文件加载去重状态"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.seen_urls = set(data.get("seen_urls", []))
                    self.seen_hashes = set(data.get("seen_hashes", []))
                logger.debug(f"去重状态已加载: {len(self.seen_urls)} URLs, "
                             f"{len(self.seen_hashes)} hashes")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"去重文件损坏，使用空状态: {e}")
                self.seen_urls = set()
                self.seen_hashes = set()

    def stats(self) -> dict:
        """返回当前去重统计"""
        return {
            "seen_urls": len(self.seen_urls),
            "seen_hashes": len(self.seen_hashes),
        }


# ============================================================
# 批量清洗 + 去重
# ============================================================

def clean_and_dedup(
    articles: List[dict],
    dedup: Deduplicator = None,
) -> List[dict]:
    """
    对一批原始文章执行 清洗 → 去重。

    Args:
        articles: crawler.fetch_all_news() 返回的原始列表
        dedup: 去重器实例，None 则临时创建（不持久化）

    Returns:
        清洗后的新文章列表（已去除重复和空内容）
    """
    if dedup is None:
        dedup = Deduplicator()

    result: List[dict] = []
    skipped_dup = 0
    skipped_invalid = 0

    for raw in articles:
        # Step 1: 清洗（返回 None = 文章无效）
        item = clean_article(raw)
        if item is None:
            skipped_invalid += 1
            logger.info(f"  丢弃无效文章: {raw.get('title', '')[:40]}")
            continue

        # Step 2: URL 去重（同一 URL 不重复采集）
        if item["url"] in getattr(dedup, "seen_urls", set()):
            skipped_dup += 1
            logger.info(f"  重复跳过: {item['title'][:40]}")
            continue

        # Step 3: 记录 + 保留
        dedup.mark_seen(item["url"])
        result.append(item)

    logger.info(f"清洗完成: 保留 {len(result)} 篇, "
                 f"跳过重复 {skipped_dup} 篇, 丢弃无效 {skipped_invalid} 篇")
    return result
