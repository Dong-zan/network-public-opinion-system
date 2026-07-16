import unittest
from datetime import datetime

from backend_app.models.event import Event
from scripts.generate_event_names import (
    RepresentativeArticle,
    build_ai_context,
    generate_event_name,
    normalize_event_name,
    parse_args,
)


class StubDeepSeekProvider:
    provider_name = "unknown"

    def __init__(self, answer="美国袭击伊朗事件"):
        self.answer = answer
        self.context = None

    def ask(self, context):
        self.context = context
        self.provider_name = "deepseek"
        return {"answer": self.answer}


class EventNameGenerationTests(unittest.TestCase):
    def setUp(self):
        self.event = Event(
            event_id=10,
            title="原新闻标题",
            summary="事件摘要",
            update_time=datetime(2026, 7, 17, 9, 0),
        )
        self.articles = [
            RepresentativeArticle(
                news_id=1,
                title="美国攻击伊朗",
                summary="报道摘要一",
                source="来源一",
                publish_time="2026-07-17 08:00:00",
            ),
            RepresentativeArticle(
                news_id=2,
                title="伊朗外交部回应",
                summary="报道摘要二",
                source="来源二",
                publish_time="2026-07-17 09:00:00",
            ),
        ]

    def test_generate_uses_deepseek_answer_and_summary_only(self):
        provider = StubDeepSeekProvider()

        result = generate_event_name(provider, self.event, self.articles)

        self.assertEqual(result, "美国袭击伊朗事件")
        sent_articles = provider.context["event"]["articles"]
        self.assertEqual(len(sent_articles), 2)
        self.assertEqual(sent_articles[0]["content"], "报道摘要一")
        self.assertNotIn("analysis", sent_articles[0])

    def test_normalize_rejects_invalid_names(self):
        with self.assertRaises(ValueError):
            normalize_event_name("这是一个超过二十个字且不符合规范的事件名称事件")
        with self.assertRaises(ValueError):
            normalize_event_name("美国袭击伊朗")

    def test_dry_run_and_existing_name_options(self):
        defaults = parse_args([])
        dry_run = parse_args(["--dry-run", "--event-id", "10", "--overwrite"])

        self.assertTrue(defaults.skip_existing)
        self.assertTrue(dry_run.dry_run)
        self.assertEqual(dry_run.event_id, 10)
        self.assertFalse(dry_run.skip_existing)

    def test_context_contains_no_more_than_supplied_representatives(self):
        context = build_ai_context(self.event, self.articles)

        self.assertEqual(context["event"]["event_id"], 10)
        self.assertEqual(len(context["event"]["articles"]), 2)
        self.assertIn("不超过20个字", context["question"])


if __name__ == "__main__":
    unittest.main()
