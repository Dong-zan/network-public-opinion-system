"""Text preprocessing utilities for news analysis.

The preprocessing module is the first step of the analysis pipeline. It accepts
one raw news item from the backend, normalizes its metadata, cleans title and
content, merges the analysable text, and returns tokens for later keyword,
sentiment, similarity and lifecycle tasks.
"""

from datetime import date, datetime
from html import unescape
import re
from typing import Any, Dict, List

try:
    import jieba
except ImportError:  # pragma: no cover - optional dependency fallback
    jieba = None


STOPWORDS = {
    "的",
    "了",
    "和",
    "是",
    "在",
    "就",
    "也",
    "有",
    "与",
    "对",
    "中",
    "为",
    "等",
    "及",
    "或",
    "一个",
    "我们",
    "你们",
    "他们",
    "进行",
    "相关",
    "表示",
    "记者",
    "报道",
    "新闻",
    "来源",
    "时间",
    "链接",
    "网页",
    "发布",
}

DOMAIN_WORDS = {
    "人工智能",
    "网络安全",
    "官方回应",
    "官方通报",
    "突发",
    "事故",
    "火灾",
    "救援",
    "调查",
    "通报",
    "回应",
    "网友",
    "关注",
    "现场",
    "安全",
    "管理",
    "媒体",
    "报道",
    "质疑",
    "爆料",
    "风险",
    "舆情",
    "伤亡",
    "投诉",
    "处罚",
}

REQUIRED_FIELDS = ("news_id", "title", "content", "source", "publish_time", "url")


def clean_text(text: str) -> str:
    """Clean HTML, URLs, extra spaces and obvious noise from text."""
    if not text:
        return ""

    text = unescape(str(text))
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"@\S+|#([^#]+)#", r" \1 ", text)
    text = re.sub(r"[\u200b-\u200f\ufeff]", " ", text)
    text = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9，。！？；：、,.!?;:]", " ", text)
    text = re.sub(r"\s+([，。！？；：、,.!?;:])", r"\1", text)
    text = re.sub(r"([，。！？；：、,.!?;:]){2,}", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_source(source: Any) -> str:
    """Normalize the news source/platform field."""
    return clean_text(str(source or "")).strip(" ，。,.")


def normalize_url(url: Any) -> str:
    """Normalize a news URL without trying to verify network reachability."""
    if not url:
        return ""
    value = str(url).strip()
    value = re.sub(r"[\s，。；;]+$", "", value)
    return value


def normalize_publish_time(publish_time: Any) -> str:
    """Normalize publish time into a stable string when possible."""
    if not publish_time:
        return ""
    if isinstance(publish_time, datetime):
        return publish_time.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(publish_time, date):
        return publish_time.strftime("%Y-%m-%d")

    value = str(publish_time).strip()
    if not value:
        return ""
    value = value.replace("年", "-").replace("月", "-").replace("日", " ")
    value = value.replace("/", "-").replace("T", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def merge_title_content(news: Dict) -> str:
    """Merge title and content so the title receives natural extra weight."""
    title = clean_text(news.get("title", ""))
    content = clean_text(news.get("content", ""))
    if title and content:
        return f"{title}。{content}".strip("。")
    return title or content


def tokenize(text: str) -> List[str]:
    """Tokenize Chinese text and remove short/noisy stop words."""
    cleaned = clean_text(text)
    if not cleaned:
        return []

    if jieba:
        raw_tokens = jieba.lcut(cleaned)
    else:
        raw_tokens = []
        for word in DOMAIN_WORDS:
            if word in cleaned:
                raw_tokens.append(word)
        raw_tokens.extend(re.findall(r"[a-zA-Z0-9]+", cleaned))

    tokens = []
    for token in raw_tokens:
        token = token.strip()
        if len(token) < 2:
            continue
        if token in STOPWORDS:
            continue
        if re.fullmatch(r"\d+", token):
            continue
        tokens.append(token)
    return tokens


def find_missing_fields(news: Dict) -> List[str]:
    """Return required fields that are absent or empty in one news item."""
    missing = []
    for field in REQUIRED_FIELDS:
        value = news.get(field)
        if value is None or str(value).strip() == "":
            missing.append(field)
    return missing


def preprocess_news(news: Dict) -> Dict:
    """Return normalized metadata, analysable text and tokens for one news item."""
    clean_title = clean_text(news.get("title", ""))
    clean_content = clean_text(news.get("content", ""))
    source = normalize_source(news.get("source", ""))
    publish_time = normalize_publish_time(news.get("publish_time", ""))
    url = normalize_url(news.get("url", ""))
    text = merge_title_content(news)
    tokens = tokenize(text)

    return {
        "news_id": news.get("news_id"),
        "title": clean_title,
        "content": clean_content,
        "source": source,
        "publish_time": publish_time,
        "url": url,
        "text": text,
        "tokens": tokens,
        "token_count": len(tokens),
        "missing_fields": find_missing_fields(news),
    }


def preprocess_news_batch(news_list: List[Dict]) -> List[Dict]:
    """Preprocess multiple news items for backend batch analysis."""
    return [preprocess_news(news) for news in news_list]
