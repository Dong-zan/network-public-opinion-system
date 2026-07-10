"""Runnable demo for the day-1 preprocessing task."""

import json
import sys
from pathlib import Path

if __package__:
    from .preprocess import preprocess_news
else:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))
    from analysis.preprocess import preprocess_news


SAMPLE_NEWS = {
    "news_id": 1001,
    "title": "【突发】某地火灾事故引发网友关注",
    "content": "<p>当地消防部门迅速开展救援。</p> 详情见 https://example.com/raw 。官方称事故原因正在调查。",
    "source": "本地新闻客户端",
    "publish_time": "2026年07月09日 08:30",
    "url": "https://example.com/news/1001",
}


if __name__ == "__main__":
    result = preprocess_news(SAMPLE_NEWS)
    print(json.dumps(result, ensure_ascii=False, indent=2))
