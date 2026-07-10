"""Unified NLP analysis pipeline used by the backend."""

from typing import Dict, List

from .heat_score import calculate_heat_score, judge_risk_level
from .keyword_extract import extract_keywords
from .lifecycle import predict_lifecycle
from .preprocess import preprocess_news
from .sentiment import analyze_sentiment
from .similarity import find_similar_news
from .summary import generate_summary


def analyze_news(news: Dict, all_news: List[Dict] | None = None, previous_heat_score: int | None = None) -> Dict:
    """
    Analyze one news item and return the agreed backend interface format.

    Input news format:
    {
        "news_id": 1001,
        "title": "新闻标题",
        "content": "新闻正文",
        "source": "新闻来源平台",
        "publish_time": "2026-07-09 10:30:00",
        "url": "https://example.com/news/1001",
    }
    """
    all_news = all_news or [news]
    processed = preprocess_news(news)
    text = processed["text"]

    keywords = extract_keywords(text, top_k=5)
    summary = generate_summary(news, keywords)
    sentiment = analyze_sentiment(text)
    similar_news = find_similar_news(news, all_news)
    heat_score = calculate_heat_score(keywords, sentiment, similar_news)
    risk_level = judge_risk_level(heat_score, sentiment)
    stage = predict_lifecycle(news, all_news, heat_score, similar_news, previous_heat_score)

    return {
        "news_id": news.get("news_id"),
        "summary": summary,
        "processed_text": text,
        "source": processed["source"],
        "publish_time": processed["publish_time"],
        "url": processed["url"],
        "missing_fields": processed["missing_fields"],
        "keywords": keywords,
        "sentiment": sentiment,
        "heat_score": heat_score,
        "stage": stage,
        "risk_level": risk_level,
        "similar_news": similar_news,
    }


def analyze_news_batch(news_list: List[Dict], previous_heat_scores: Dict | None = None) -> List[Dict]:
    """
    Analyze a list of news items and return one result per item.

    previous_heat_scores is optional. The backend can pass a mapping such as
    {1001: 80} so lifecycle prediction can identify a declining event.
    """
    previous_heat_scores = previous_heat_scores or {}
    return [
        analyze_news(news, news_list, previous_heat_scores.get(news.get("news_id")))
        for news in news_list
    ]
