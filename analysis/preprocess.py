"""Text preprocessing utilities for news analysis."""

from datetime import date, datetime
from html import unescape
import re
from typing import Any, Dict, List

from .dependencies import get_jieba
from .lexicon import load_domain_words, load_stopwords


REQUIRED_FIELDS = ("news_id", "title", "content", "source", "publish_time", "url")
TIME_FALLBACK_FIELDS = ("publish_time", "crawl_time", "created_at")
VALUABLE_NUMBER_PATTERN = re.compile(
    r"^\d+(?:\.\d+)?(?:%|％|年|月|日|时|分|秒|小时|天|人|名|例|起|件|万|亿|元|级|号|次|个|条|岁)$"
)

_DOMAIN_WORDS_REGISTERED = False


def _ensure_domain_words_registered() -> None:
    """Add domain words to jieba once so domain phrases are not split apart."""
    global _DOMAIN_WORDS_REGISTERED
    if _DOMAIN_WORDS_REGISTERED:
        return

    jieba = get_jieba()
    for word in load_domain_words():
        jieba.add_word(word)
    _DOMAIN_WORDS_REGISTERED = True


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
    text = re.sub(
        r"[^\u4e00-\u9fa5a-zA-Z0-9，。！？；：、,.!?;:%％年月日时分秒万亿千百十人名例起件元级号次个条岁-]",
        " ",
        text,
    )
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


def get_effective_time(news: Dict) -> str:
    """Return publish_time, or the best available backend collection time."""
    for field in TIME_FALLBACK_FIELDS:
        normalized = normalize_publish_time(news.get(field, ""))
        if normalized:
            return normalized
    return ""


def merge_title_content(news: Dict) -> str:
    """Merge title and content so the title receives natural extra weight."""
    title = clean_text(news.get("title", ""))
    content = clean_text(news.get("content", ""))
    if title and content and content.startswith(title):
        return content
    if title and content:
        return f"{title}。{content}".strip("。")
    return title or content


def _is_low_value_number(token: str) -> bool:
    if not re.search(r"\d", token):
        return False
    if VALUABLE_NUMBER_PATTERN.fullmatch(token):
        return False
    return bool(re.fullmatch(r"\d+(?:\.\d+)?", token))


def tokenize(text: str) -> List[str]:
    """Tokenize Chinese text and remove short/noisy stop words."""
    cleaned = clean_text(text)
    if not cleaned:
        return []

    _ensure_domain_words_registered()
    raw_tokens = get_jieba().lcut(cleaned)
    stopwords = load_stopwords()

    tokens = []
    for token in raw_tokens:
        token = token.strip()
        if len(token) < 2:
            continue
        if token in stopwords:
            continue
        if _is_low_value_number(token):
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
    effective_time = get_effective_time(news)
    url = normalize_url(news.get("url", ""))
    text = merge_title_content(news)
    tokens = tokenize(text)

    return {
        "news_id": news.get("news_id"),
        "title": clean_title,
        "content": clean_content,
        "source": source,
        "publish_time": publish_time,
        "effective_time": effective_time,
        "url": url,
        "text": text,
        "tokens": tokens,
        "token_count": len(tokens),
        "missing_fields": find_missing_fields(news),
    }


def preprocess_news_batch(news_list: List[Dict]) -> List[Dict]:
    """Preprocess multiple news items for backend batch analysis."""
    return [preprocess_news(news) for news in news_list]
