import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    requests_stub = types.ModuleType("requests")
    requests_stub.Session = object
    requests_stub.Response = object
    requests_stub.RequestException = Exception
    requests_stub.post = None
    sys.modules["requests"] = requests_stub

try:
    import bs4  # noqa: F401
except ModuleNotFoundError:
    bs4_stub = types.ModuleType("bs4")
    bs4_stub.BeautifulSoup = object
    sys.modules["bs4"] = bs4_stub

from crawler.replay import replay_articles


class ReplayLimitTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.json_file = Path(self.temp_dir.name) / "articles.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_articles(self, count):
        articles = [{"title": f"文章 {index}"} for index in range(count)]
        self.json_file.write_text(
            json.dumps(articles, ensure_ascii=False),
            encoding="utf-8",
        )
        return articles

    @patch("crawler.replay._upload_to_backend")
    def test_without_limit_replays_all_articles(self, upload):
        articles = self.write_articles(3)
        upload.return_value = len(articles)

        result = replay_articles(str(self.json_file))

        self.assertEqual(result, (3, 3))
        self.assertEqual(upload.call_args.args[0], articles)

    @patch("crawler.replay._upload_to_backend")
    def test_limit_replays_only_requested_articles(self, upload):
        articles = self.write_articles(120)
        upload.return_value = 100

        result = replay_articles(str(self.json_file), limit=100)

        self.assertEqual(result, (100, 100))
        self.assertEqual(upload.call_args.args[0], articles[:100])

    @patch("crawler.replay._upload_to_backend")
    def test_limit_larger_than_article_count_replays_all_articles(self, upload):
        articles = self.write_articles(3)
        upload.return_value = len(articles)

        result = replay_articles(str(self.json_file), limit=100)

        self.assertEqual(result, (3, 3))
        self.assertEqual(upload.call_args.args[0], articles)


if __name__ == "__main__":
    unittest.main()
