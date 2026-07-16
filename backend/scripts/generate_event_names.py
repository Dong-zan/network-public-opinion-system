"""Generate concise event display names through the configured DeepSeek service.

This is an offline display-data backfill. It does not participate in event
aggregation or change event IDs, embeddings, heat, or lifecycle fields.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from sqlalchemy import inspect


BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


from backend_app.database import SessionLocal, engine
from backend_app.models.analysis import Analysis
from backend_app.models.article import Article
from backend_app.models.event import Event
from backend_app.services.ai_provider import RealAIProvider


MAX_ARTICLES = 5
MAX_EVENT_NAME_LENGTH = 20
NAME_SUFFIXES = ("事件", "风波", "发布")
EVENT_NAME_QUESTION = """
请综合当前事件下全部已提供的多篇新闻，生成一个简洁、专业的中文事件名称。
要求：
1. 不超过20个字；
2. 不使用标题党语言；
3. 突出核心人物、组织、地点和事件动作；
4. 使用“XX事件”“XX风波”或“XX发布”形式；
5. 不包含时间和媒体名称；
6. 只返回事件名称，不要解释、引号、Markdown或其他文字。
""".strip()


@dataclass(frozen=True)
class RepresentativeArticle:
    news_id: int
    title: str
    summary: str
    source: str
    publish_time: str | None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Use the configured DeepSeek AI service to backfill events.event_name.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and print names without writing to the database.",
    )
    parser.add_argument(
        "--event-id",
        type=int,
        help="Process only the specified event ID.",
    )
    existing_group = parser.add_mutually_exclusive_group()
    existing_group.add_argument(
        "--skip-existing",
        dest="skip_existing",
        action="store_true",
        default=True,
        help="Skip events that already have event_name (default).",
    )
    existing_group.add_argument(
        "--overwrite",
        dest="skip_existing",
        action="store_false",
        help="Regenerate and overwrite existing event_name values.",
    )
    return parser.parse_args(argv)


def has_event_name_column() -> bool:
    columns = inspect(engine).get_columns(Event.__tablename__)
    return any(column["name"] == "event_name" for column in columns)


def select_representative_articles(db, event_id: int) -> list[RepresentativeArticle]:
    rows = (
        db.query(Article, Analysis)
        .outerjoin(Analysis, Analysis.news_id == Article.news_id)
        .filter(Article.event_id == event_id)
        .order_by(
            Analysis.heat_score.desc(),
            Article.is_official.desc(),
            Article.publish_time.desc(),
            Article.news_id.desc(),
        )
        .limit(MAX_ARTICLES)
        .all()
    )

    selected = []
    seen_news_ids = set()
    for article, analysis in rows:
        if article.news_id in seen_news_ids:
            continue
        seen_news_ids.add(article.news_id)
        summary = (
            analysis.summary
            if analysis is not None and analysis.summary
            else (article.content or "")[:500]
        )
        selected.append(
            RepresentativeArticle(
                news_id=article.news_id,
                title=(article.title or "").strip(),
                summary=summary.strip(),
                source=(article.source or "").strip(),
                publish_time=(
                    article.publish_time.isoformat(sep=" ")
                    if article.publish_time is not None
                    else None
                ),
            )
        )
    return selected


def build_ai_context(
    event: Event,
    articles: Sequence[RepresentativeArticle],
) -> dict:
    return {
        "event": {
            "event_id": event.event_id,
            "title": event.title or "",
            "summary": event.summary or "",
            "update_time": (
                event.update_time.isoformat(sep=" ")
                if event.update_time is not None
                else None
            ),
            "articles": [
                {
                    "news_id": article.news_id,
                    "title": article.title,
                    # The AI service expects article text in `content`; this script
                    # intentionally sends only the stored NLP summary/snippet.
                    "content": article.summary,
                    "source": article.source,
                    "publish_time": article.publish_time,
                }
                for article in articles
            ],
            "analysis": {},
        },
        "question": EVENT_NAME_QUESTION,
    }


def normalize_event_name(raw_name: str) -> str:
    if not isinstance(raw_name, str):
        raise ValueError("AI service did not return a text event name")

    value = raw_name.strip()
    value = re.sub(r"^```(?:text|plaintext)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value)
    value = re.sub(r"^事件名称\s*[:：]\s*", "", value)
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError("AI service must return exactly one event name")

    value = lines[0].strip(" 《》“”\"'").rstrip("。！？!?;；")
    value = re.sub(r"\s+", "", value)
    if not value:
        raise ValueError("AI service returned an empty event name")
    if len(value) > MAX_EVENT_NAME_LENGTH:
        raise ValueError(
            f"AI event name exceeds {MAX_EVENT_NAME_LENGTH} characters: {value}",
        )
    if not value.endswith(NAME_SUFFIXES):
        raise ValueError("事件名称必须以“事件”“风波”或“发布”结尾")
    return value


def generate_event_name(
    provider: RealAIProvider,
    event: Event,
    articles: Sequence[RepresentativeArticle],
) -> str:
    if not articles:
        raise ValueError("当前事件没有可用的关联新闻")

    response = provider.ask(build_ai_context(event, articles))
    if provider.provider_name != "deepseek":
        raise RuntimeError(
            f"Event names require DeepSeek, but AI service used {provider.provider_name!r}",
        )
    raw_name = response.get("answer") if isinstance(response, dict) else None
    return normalize_event_name(raw_name)


def process_event(db, provider: RealAIProvider, event_id: int, dry_run: bool) -> str:
    event = db.query(Event).filter(Event.event_id == event_id).first()
    if event is None:
        raise ValueError(f"Event {event_id} does not exist")

    articles = select_representative_articles(db, event_id)
    event_name = generate_event_name(provider, event, articles)
    if not dry_run:
        event.event_name = event_name
        db.commit()
    return event_name


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not has_event_name_column():
        print(
            "events.event_name does not exist. Apply backend/migrate_add_event_name.sql first.",
            file=sys.stderr,
        )
        return 2

    db = SessionLocal()
    provider = RealAIProvider()
    failed = 0
    generated = 0
    skipped = 0

    try:
        event_query = db.query(Event.event_id, Event.event_name)
        if args.event_id is not None:
            event_query = event_query.filter(Event.event_id == args.event_id)
        event_rows = event_query.order_by(Event.event_id.asc()).all()

        if args.event_id is not None and not event_rows:
            print(f"Event {args.event_id} does not exist.", file=sys.stderr)
            return 1

        for event_id, existing_name in event_rows:
            if args.skip_existing and existing_name and existing_name.strip():
                skipped += 1
                print(f"[skip] event_id={event_id} event_name={existing_name}")
                continue

            try:
                event_name = process_event(db, provider, event_id, args.dry_run)
                generated += 1
                action = "dry-run" if args.dry_run else "saved"
                print(f"[{action}] event_id={event_id} event_name={event_name}")
            except Exception as exc:  # Keep the batch moving after one event fails.
                db.rollback()
                failed += 1
                print(f"[failed] event_id={event_id} error={exc}", file=sys.stderr)
    finally:
        db.close()

    print(f"generated={generated} skipped={skipped} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
