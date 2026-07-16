import unittest

from backend_app.services.verification_assessment import enrich_verification_result


def build_context(articles, keywords=None):
    return {
        "event": {
            "title": "英格兰对阵阿根廷世界杯半决赛",
            "articles": articles,
            "analysis": {"keywords": keywords or ["英格兰", "阿根廷", "世界杯"]},
        }
    }


def article(index, source="微博", platform="微博", account_type="个人", official=False):
    return {
        "news_id": index,
        "title": f"英格兰对阵阿根廷世界杯半决赛消息{index}",
        "content": "英格兰与阿根廷进行世界杯半决赛",
        "source": source,
        "platform": platform,
        "account_id": f"account-{index}",
        "account_type": account_type,
        "is_official": official,
        "url": f"https://example.com/{index}",
        "publish_time": f"2026-07-16 1{index % 10}:00:00",
    }


class VerificationAssessmentTests(unittest.TestCase):
    def test_multiple_weibo_sources_are_high_with_general_completeness(self):
        result = enrich_verification_result(
            {"overall_verdict": "insufficient_evidence", "verification_coverage": 20},
            build_context([article(1), article(2), article(3)]),
        )

        self.assertEqual(result["authenticity_assessment"]["label"], "高")
        self.assertEqual(result["evidence_completeness"]["label"], "一般")
        self.assertEqual(result["authenticity_assessment"]["factors"]["official_count"], 0)

    def test_single_news_source_is_medium(self):
        result = enrich_verification_result(
            {"overall_verdict": "supported", "verification_coverage": 100},
            build_context([
                article(1, source="新闻网站", platform="新闻网站", account_type="新闻媒体"),
            ]),
        )

        self.assertEqual(result["authenticity_assessment"]["label"], "中")

    def test_official_confirmation_is_high(self):
        result = enrich_verification_result(
            {"overall_verdict": "supported", "verification_coverage": 100},
            build_context([
                article(1, source="政府发布", platform="政务", account_type="官方", official=True),
            ]),
        )

        self.assertEqual(result["authenticity_assessment"]["label"], "高")
        self.assertEqual(result["authenticity_assessment"]["factors"]["official_count"], 1)

    def test_conflicting_sources_cap_authenticity_at_suspicious(self):
        result = enrich_verification_result(
            {"overall_verdict": "conflicting", "verification_coverage": 100},
            build_context([
                article(1),
                article(2, source="新闻网站", platform="新闻网站", account_type="新闻媒体"),
                article(3, source="政府发布", platform="政务", account_type="官方", official=True),
            ]),
        )

        self.assertEqual(result["authenticity_assessment"]["label"], "存疑")
        self.assertLess(result["authenticity_assessment"]["score"], 55)
        self.assertTrue(result["authenticity_assessment"]["factors"]["source_conflict"])

    def test_explicit_debunking_is_low(self):
        result = enrich_verification_result(
            {"overall_verdict": "contradicted", "verification_coverage": 100},
            build_context([article(1), article(2), article(3)]),
        )

        self.assertEqual(result["authenticity_assessment"]["label"], "低")


if __name__ == "__main__":
    unittest.main()
