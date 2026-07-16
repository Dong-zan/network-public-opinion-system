"""将已有crawler JSON文件重新逐篇推送到backend。"""

import argparse
import json
from pathlib import Path

from crawler.config import BACKEND_URL
from crawler.pipeline import _upload_to_backend


def replay_articles(
    json_file: str,
    backend_url: str = None,
    limit: int = None,
) -> tuple[int, int]:
    filepath = Path(json_file)
    with filepath.open("r", encoding="utf-8") as file:
        articles = json.load(file)

    if not isinstance(articles, list):
        raise ValueError("crawler JSON顶层必须是文章数组")

    if limit is not None:
        articles = articles[:limit]

    success_count = _upload_to_backend(
        articles,
        backend_url=backend_url or BACKEND_URL,
    )
    return success_count, len(articles)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="读取已有crawler JSON并重新逐篇POST /internal/articles",
    )
    parser.add_argument("json_file", help="例如 output/2026-07-16.json")
    parser.add_argument(
        "--backend-url",
        default=BACKEND_URL,
        help=f"默认: {BACKEND_URL}",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="最大导入文章数量（默认全部）",
    )
    args = parser.parse_args()

    success_count, total_count = replay_articles(
        args.json_file,
        backend_url=args.backend_url,
        limit=args.limit,
    )
    print(f"replay完成：成功 {success_count} / 总计 {total_count}")
    return 0 if success_count == total_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
