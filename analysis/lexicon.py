"""Lexicon loading helpers for the analysis module."""

from functools import lru_cache
from pathlib import Path
from typing import Iterable, Set


RESOURCE_DIR = Path(__file__).resolve().parent / "resources"

DEFAULT_STOPWORDS = {
    "的", "了", "和", "是", "在", "就", "也", "有", "与", "及", "或", "等",
    "为", "被", "一个", "我们", "你们", "他们", "进行", "相关", "表示",
    "记者", "报道", "新闻", "来源", "时间", "链接", "网页", "发布",
}

DEFAULT_DOMAIN_WORDS = {
    "人工智能", "网络安全", "官方回应", "官方通报", "突发", "事故", "火灾",
    "救援", "调查", "通报", "回应", "网友", "关注", "现场", "安全", "管理",
    "媒体", "报道", "质疑", "爆料", "风险", "舆情", "伤亡", "投诉", "处罚",
}

DEFAULT_SENSITIVE_WORDS = {
    "突发", "事故", "通报", "回应", "救援", "调查", "官方", "网传", "爆料",
    "舆情", "投诉", "处罚", "风险", "伤亡", "火灾", "安全", "违法", "违规",
    "死亡", "受伤", "冲突", "危机",
}


def _clean_words(words: Iterable[str]) -> Set[str]:
    cleaned = set()
    for word in words:
        value = word.strip()
        if value and not value.startswith("#"):
            cleaned.add(value)
    return cleaned


def _load_word_file(file_name: str) -> Set[str]:
    path = RESOURCE_DIR / file_name
    if not path.exists():
        return set()

    lines = path.read_text(encoding="utf-8").splitlines()
    return _clean_words(line.split("#", 1)[0] for line in lines)


@lru_cache(maxsize=None)
def load_stopwords() -> Set[str]:
    return set(DEFAULT_STOPWORDS) | _load_word_file("stopwords.txt")


@lru_cache(maxsize=None)
def load_domain_words() -> Set[str]:
    return set(DEFAULT_DOMAIN_WORDS) | _load_word_file("domain_words.txt")


@lru_cache(maxsize=None)
def load_sensitive_words() -> Set[str]:
    return set(DEFAULT_SENSITIVE_WORDS) | _load_word_file("sensitive_words.txt")
