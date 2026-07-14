"""HTTP service for the 4号 NLP analysis module.

The backend pushes one article to POST /nlp/analyze, and this service returns
one complete analysis result using the existing analyze_news() pipeline.
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from typing import Any, Dict, List
from urllib.parse import urlparse

if __package__:
    from .analysis_pipeline import analyze_news
    from .dependencies import AnalysisDependencyError
else:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))
    from analysis.analysis_pipeline import analyze_news
    from analysis.dependencies import AnalysisDependencyError


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 9000
ANALYZE_PATHS = {"/nlp/analyze"}
HEALTH_PATH = "/health"
REQUIRED_KEYS = ("news_id", "title", "content", "source", "publish_time", "url")
NON_EMPTY_KEYS = ("news_id", "title", "content", "source")


def _json_bytes(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def _validate_payload(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("请求体必须是 JSON 对象")

    missing = [key for key in REQUIRED_KEYS if key not in payload]
    empty = [key for key in NON_EMPTY_KEYS if key in payload and str(payload.get(key) or "").strip() == ""]
    problems = missing + empty
    if problems:
        raise ValueError("缺少必要字段：" + "、".join(problems))

    news = dict(payload)
    # Keep publish_time/url in the contract, but tolerate null values from real crawlers.
    if news.get("publish_time") is None:
        news["publish_time"] = ""
    if news.get("url") is None:
        news["url"] = ""
    return news


def _candidate_news(news: Dict[str, Any]) -> List[Dict[str, Any]]:
    all_news = news.get("all_news")
    if isinstance(all_news, list):
        candidates = [item for item in all_news if isinstance(item, dict)]
        if not any(item.get("news_id") == news.get("news_id") for item in candidates):
            candidates.insert(0, news)
        return candidates
    return [news]


def analyze_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate backend input and return the complete analysis result."""
    news = _validate_payload(payload)
    previous_heat_score = news.get("previous_heat_score")
    result = analyze_news(news, _candidate_news(news), previous_heat_score)
    # similar_news must stay a news_id list, not a list of news objects.
    result["similar_news"] = [item for item in result.get("similar_news", []) if item is not None]
    return result


class NLPRequestHandler(BaseHTTPRequestHandler):
    server_version = "NLPAnalysisHTTP/1.0"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API name.
        path = urlparse(self.path).path
        if path == HEALTH_PATH:
            self._send_json(200, {"status": "ok"})
            return
        self._send_json(404, {"error": "not_found", "message": "仅支持 GET /health 和 POST /nlp/analyze"})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API name.
        path = urlparse(self.path).path
        if path not in ANALYZE_PATHS:
            self._send_json(404, {"error": "not_found", "message": "请 POST 到 /nlp/analyze"})
            return

        try:
            payload = self._read_json_body()
            result = analyze_request(payload)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "bad_request", "message": "请求体不是合法 JSON"})
            return
        except ValueError as exc:
            self._send_json(400, {"error": "bad_request", "message": str(exc)})
            return
        except AnalysisDependencyError as exc:
            self._send_json(500, {"error": "dependency_error", "message": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 - service should return readable integration errors.
            self._send_json(500, {"error": "analysis_error", "message": f"NLP 分析失败：{exc}"})
            return

        print("返回给后端的 NLP 分析结果：", flush=True)
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        self._send_json(200, result)

    def _read_json_body(self) -> Any:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw_body = self.rfile.read(length).decode("utf-8")
        return json.loads(raw_body or "{}")

    def _send_json(self, status_code: int, data: Any) -> None:
        body = _json_bytes(data)
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    server = ThreadingHTTPServer((host, port), NLPRequestHandler)
    print(f"4号 NLP 分析接口已启动：http://{host}:{port}/nlp/analyze")
    print("后端 POST 新闻 JSON 后，服务会同步返回完整 analysis 结果。按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止 4号 NLP 分析接口。")
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the NLP analysis HTTP service.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind. Default: 0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind. Default: 9000")
    args = parser.parse_args()
    run_server(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

