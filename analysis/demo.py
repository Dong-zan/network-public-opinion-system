"""Small runnable demo for the NLP intelligent analysis module."""

import json
import sys
from pathlib import Path

if __package__:
    from .analysis_pipeline import analyze_news_batch
else:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))
    from analysis.analysis_pipeline import analyze_news_batch


SAMPLE_NEWS = [
    {
        "news_id": 1001,
        "title": "某地突发火灾事故引发关注",
        "content": "当地消防部门迅速开展救援，官方发布通报称事故原因正在调查。",
        "source": "本地新闻客户端",
        "publish_time": "2026-07-09 08:30:00",
        "url": "https://example.com/news/1001",
    },
    {
        "news_id": 1002,
        "title": "官方通报某地火灾救援进展",
        "content": "现场救援持续进行，相关部门回应网友关切，事故原因仍在调查。",
        "source": "官方发布",
        "publish_time": "2026-07-09 09:20:00",
        "url": "https://example.com/news/1002",
    },
    {
        "news_id": 1003,
        "title": "网友关注某地火灾事故原因",
        "content": "多家媒体报道该火灾事故，部分网友质疑现场安全管理问题。",
        "source": "社交平台",
        "publish_time": "2026-07-09 10:10:00",
        "url": "https://example.com/news/1003",
    },
    {
        "news_id": 1004,
        "title": "本地学校举办科技活动",
        "content": "学生参与人工智能体验课程，活动现场气氛热烈。",
        "source": "教育频道",
        "publish_time": "2026-07-09 11:00:00",
        "url": "https://example.com/news/1004",
    },
]


if __name__ == "__main__":
    results = analyze_news_batch(SAMPLE_NEWS)
    print(json.dumps(results, ensure_ascii=False, indent=2))
