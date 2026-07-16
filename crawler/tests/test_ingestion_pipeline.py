import sys
import types
import unittest
from unittest.mock import Mock, patch

try:
    import bs4  # noqa: F401
except ModuleNotFoundError:
    bs4_stub = types.ModuleType("bs4")
    bs4_stub.BeautifulSoup = object
    sys.modules["bs4"] = bs4_stub

from crawler.cleaner import clean_article
from crawler.crawler import _decode_response_content
from crawler.pipeline import _upload_to_backend
from crawler.utils import normalize_publish_time


class PublishTimeTests(unittest.TestCase):
    def test_normal_publish_time_is_normalized(self):
        self.assertEqual(
            normalize_publish_time("2026-07-13 22:01:00"),
            "2026-07-13 22:01:00",
        )

    def test_mojibake_publish_time_becomes_none(self):
        self.assertIsNone(
            normalize_publish_time("2026е№ҙ07жңҲ13ж—Ҙ 22:01гҖҖ"),
        )

    def test_clean_article_keeps_article_but_drops_invalid_time(self):
        article = clean_article(
            {
                "title": "正常新闻标题",
                "content": "这是一段长度足够的新闻正文，" * 10,
                "source": "中新网",
                "url": "https://example.test/bad-time",
                "publish_time": "2026е№ҙ07жңҲ13ж—Ҙ 22:01гҖҖ",
            }
        )

        self.assertIsNotNone(article)
        self.assertIsNone(article["publish_time"])


class ResponseDecodingTests(unittest.TestCase):
    def test_utf8_content_is_not_corrupted_by_wrong_apparent_encoding(self):
        response = Mock()
        response.content = "2026年07月13日 中文新闻".encode("utf-8")
        response.apparent_encoding = "windows-1251"
        response.encoding = None

        decoded = _decode_response_content(response, "utf-8")

        self.assertEqual(decoded, "2026年07月13日 中文新闻")


class BackendUploadIsolationTests(unittest.TestCase):
    @patch("crawler.pipeline.requests.post")
    def test_one_failed_article_does_not_block_next_article(self, post):
        failed_response = Mock(status_code=500, text="invalid article")
        success_response = Mock(status_code=200, text='{"data":{"news_ids":[9]}}')
        success_response.json.return_value = {"data": {"news_ids": [9]}}
        post.side_effect = [failed_response, success_response]

        uploaded = _upload_to_backend(
            [
                {
                    "title": "乱码时间文章",
                    "url": "https://example.test/1",
                    "publish_time": "2026е№ҙ07жңҲ13ж—Ҙ",
                },
                {
                    "title": "正常文章",
                    "url": "https://example.test/2",
                    "publish_time": "2026-07-13 22:01:00",
                },
            ],
            backend_url="https://backend.test/internal/articles",
        )

        self.assertEqual(uploaded, 1)
        self.assertEqual(post.call_count, 2)
        self.assertIsNone(post.call_args_list[0].kwargs["json"][0]["publish_time"])
        self.assertEqual(
            post.call_args_list[1].kwargs["json"][0]["publish_time"],
            "2026-07-13 22:01:00",
        )


if __name__ == "__main__":
    unittest.main()
