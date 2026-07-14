import logging
from datetime import datetime
from typing import Any

import requests
from pydantic import ValidationError

from backend_app.config import settings
from backend_app.schemas.analysis import AnalysisCreate


logger = logging.getLogger(__name__)


class NLPClientError(RuntimeError):
    """Raised when the external NLP service cannot return a usable result."""


class NLPClient:
    def __init__(
        self,
        server_url: str | None = None,
        timeout: float = 30,
    ):
        self.server_url = (
            server_url
            if server_url is not None
            else settings.NLP_SERVER_URL
        ).strip()
        self.timeout = timeout

    def analyze(self, article: Any) -> AnalysisCreate:
        if not self.server_url:
            raise NLPClientError("NLP_SERVER_URL is not configured")

        response = requests.post(
            self.server_url,
            json=self._build_payload(article),
            timeout=self.timeout,
        )

        try:
            response.raise_for_status()
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise NLPClientError(
                "NLP service request failed or returned invalid JSON"
            ) from exc

        result = body.get("data", body) if isinstance(body, dict) else body

        if not isinstance(result, dict):
            raise NLPClientError("NLP service response must be a JSON object")

        try:
            analysis = AnalysisCreate.model_validate(result)
        except ValidationError as exc:
            raise NLPClientError("NLP service response validation failed") from exc

        if analysis.news_id != article.news_id:
            raise NLPClientError("NLP service returned a mismatched news_id")

        return analysis

    @staticmethod
    def _build_payload(article: Any) -> dict[str, Any]:
        publish_time = article.publish_time

        if isinstance(publish_time, datetime):
            publish_time = publish_time.isoformat()

        return {
            "news_id": article.news_id,
            "title": article.title,
            "content": article.content,
            "source": article.source,
            "url": article.url,
            "publish_time": publish_time,
            "platform": article.platform,
            "author": article.author,
            "account_id": article.account_id,
            "account_name": article.account_name,
            "account_type": article.account_type,
            "is_official": article.is_official,
            "repost_count": article.repost_count,
            "comment_count": article.comment_count,
            "like_count": article.like_count,
        }
