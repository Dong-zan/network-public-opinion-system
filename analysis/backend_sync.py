"""Backend integration helper for the NLP analysis module.

This script pulls pending articles from the backend, runs the local NLP
pipeline, and posts only the agreed analysis fields back to the backend.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib import error, request

if __package__:
    from .analysis_pipeline import analyze_news_batch
else:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))
    from analysis.analysis_pipeline import analyze_news_batch


DEFAULT_BASE_URL = "http://10.122.240.155:8000"
PENDING_PATH = "/internal/articles/pending"
ANALYSIS_PATH = "/internal/analysis"
SUBMIT_FIELDS = (
    "news_id",
    "keywords",
    "sentiment",
    "heat_score",
    "stage",
    "risk_level",
    "similar_news",
)


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _read_json_response(response: Any) -> Any:
    body = response.read().decode("utf-8")
    if not body.strip():
        return {}
    return json.loads(body)


def _http_get_json(url: str, timeout: int) -> Any:
    try:
        with request.urlopen(url, timeout=timeout) as response:
            return _read_json_response(response)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} failed: HTTP {exc.code} {body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"GET {url} failed: {exc.reason}") from exc


def _http_post_json(url: str, payload: Dict[str, Any], timeout: int) -> Any:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    http_request = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(http_request, timeout=timeout) as response:
            return _read_json_response(response)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {url} failed: HTTP {exc.code} {body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"POST {url} failed: {exc.reason}") from exc


def fetch_pending_articles(base_url: str, timeout: int = 10) -> Dict[str, Any]:
    """Fetch articles that have not completed NLP analysis."""
    return _http_get_json(_join_url(base_url, PENDING_PATH), timeout)


def extract_news_list(response: Any) -> List[Dict[str, Any]]:
    """Validate the backend response and return response['data']."""
    if isinstance(response, list):
        return response
    if not isinstance(response, dict):
        raise ValueError("pending response must be a JSON object or article list")

    code = response.get("code")
    if code != 200:
        raise ValueError(f"pending response code is not 200: {code!r}, message={response.get('message')!r}")

    data = response.get("data")
    if not isinstance(data, list):
        raise ValueError("pending response data must be a list")

    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"pending response data[{index}] must be an object")
    return data


def build_submit_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only fields accepted by POST /internal/analysis."""
    payload = {field: result.get(field) for field in SUBMIT_FIELDS}
    if payload["news_id"] is None:
        raise ValueError("analysis result is missing news_id")
    if not isinstance(payload["sentiment"], dict):
        raise ValueError(f"analysis result {payload['news_id']} has invalid sentiment")
    if payload["similar_news"] is None:
        payload["similar_news"] = []
    return payload


def submit_analysis(base_url: str, payload: Dict[str, Any], timeout: int = 10) -> Any:
    """Submit one NLP analysis result to the backend."""
    response = _http_post_json(_join_url(base_url, ANALYSIS_PATH), payload, timeout)
    if isinstance(response, dict) and response.get("code", 200) != 200:
        raise RuntimeError(
            f"submit news_id={payload.get('news_id')} failed: "
            f"code={response.get('code')!r}, message={response.get('message')!r}"
        )
    return response


def _load_response_from_file(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_once(
    base_url: str = DEFAULT_BASE_URL,
    *,
    from_file: str | None = None,
    limit: int = 1,
    submit: bool = False,
    timeout: int = 10,
) -> int:
    """Run one fetch-analyze-submit cycle and return processed item count."""
    response = _load_response_from_file(from_file) if from_file else fetch_pending_articles(base_url, timeout)
    news_list = extract_news_list(response)
    if limit > 0:
        news_list = news_list[:limit]

    if not news_list:
        print("暂无待分析新闻")
        return 0

    results = analyze_news_batch(news_list)
    processed = 0
    for result in results:
        payload = build_submit_payload(result)
        if submit:
            submit_response = submit_analysis(base_url, payload, timeout)
            print(
                f"已提交 news_id={payload['news_id']}，后端响应："
                f"{json.dumps(submit_response, ensure_ascii=False)}"
            )
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        processed += 1
    return processed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync pending backend articles with the NLP analysis module.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Backend base URL.")
    parser.add_argument("--from-file", help="Read a saved pending-response JSON file instead of calling the backend.")
    parser.add_argument("--limit", type=int, default=1, help="Maximum articles to process per run. Use 0 for all.")
    parser.add_argument("--loop", action="store_true", help="Keep polling instead of running once.")
    parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds when --loop is used.")
    parser.add_argument("--timeout", type=int, default=10, help="HTTP timeout in seconds.")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", help="Print payloads without submitting. This is default.")
    mode_group.add_argument("--submit", action="store_true", help="Submit results to POST /internal/analysis.")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.loop and args.from_file:
        parser.error("--loop cannot be used with --from-file")
    if args.limit < 0:
        parser.error("--limit must be >= 0")
    if args.interval <= 0:
        parser.error("--interval must be > 0")
    if args.timeout <= 0:
        parser.error("--timeout must be > 0")

    submit = bool(args.submit)
    while True:
        try:
            run_once(
                args.base_url,
                from_file=args.from_file,
                limit=args.limit,
                submit=submit,
                timeout=args.timeout,
            )
        except Exception as exc:  # noqa: BLE001 - command line tool should report all failures cleanly.
            print(f"联调失败：{exc}", file=sys.stderr)
            if not args.loop:
                return 1

        if not args.loop:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
