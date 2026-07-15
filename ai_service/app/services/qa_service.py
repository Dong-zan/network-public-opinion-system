import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from functools import lru_cache

from app.core.config import settings
from app.llm.base import LLMProvider, LLMProviderError, LLMProviderUnavailableError
from app.llm.factory import create_llm_provider
from app.llm.prompt_types import PromptBundle
from app.llm.prompts import build_qa_prompt
from app.schemas.event import Article, EventContext, Sentiment


INSUFFICIENT = "当前信息不足"
MULTI_ARTICLE_CUES = (
    "多篇",
    "两篇",
    "所有报道",
    "全部报道",
    "综合报道",
    "综合当前",
    "分别说明",
    "各篇文章",
    "各篇新闻",
    "各自",
    "按照时间顺序",
    "按照报道发布时间",
    "不同报道",
    "报道之间",
    "多个来源",
)


@dataclass(frozen=True)
class QAResult:
    answer: str
    confidence: float = 0.0
    evidence_refs: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


class QAService:
    def __init__(
        self,
        provider: LLMProvider | None = None,
        top_k: int = 5,
        article_max_chars: int = 1000,
    ) -> None:
        self.provider = provider if provider is not None else create_llm_provider(settings.llm_provider)
        self.top_k = top_k
        self.article_max_chars = article_max_chars

    def answer(self, event: EventContext, question: str) -> QAResult:
        question = question.strip()
        if not question:
            result = QAResult(answer="问题为空，当前无法回答。", limitations=["未提供问题"])
        else:
            question_type = self._classify(event, question)
            if question_type == "multi_specified_articles":
                result = self._answer_multiple_specified_articles(event, question)
            elif question_type == "multi_evidence":
                result = self._answer_multi_article(event, question)
            elif question_type == "trend":
                result = self._answer_via_provider(event, question)
            elif question_type == "source":
                result = self._answer_sources(event, question)
            elif question_type == "source_identity":
                result = self._answer_source_identity(event, question)
            elif question_type == "article":
                result = self._answer_article(event, question)
            elif question_type == "risk":
                result = self._answer_risk(event, question)
            elif question_type == "sentiment":
                result = self._answer_sentiment(event, question)
            elif question_type == "summary":
                result = self._answer_summary(event, question)
            elif question_type == "out_of_scope":
                result = self._answer_via_provider(event, question)
            else:
                result = self._answer_from_relevant_articles(event, question)
        return self._finalize_result(result)

    def select_relevant_articles(
        self,
        event: EventContext,
        question: str,
        top_k: int | None = None,
    ) -> list[Article]:
        limit = self.top_k if top_k is None else max(top_k, 0)
        valid_articles = [article for article in event.articles if self._is_valid_article(article)]
        requested_ids = self._extract_news_ids(question)
        if self._is_multi_article_question(question) or len(requested_ids) > 1:
            return self._select_multi_articles(
                valid_articles,
                question,
                event.analysis.keywords,
                limit,
                requested_ids,
            )
        if limit == 0:
            return []
        ranked = self._rank_relevant_articles(valid_articles, question, event.analysis.keywords)
        return self._sort_by_publish_time(ranked[:limit])

    def _rank_relevant_articles(
        self,
        articles: list[Article],
        question: str,
        keywords: list[str],
    ) -> list[Article]:
        terms = self._question_terms(question, keywords)
        scored: list[tuple[int, int, Article]] = []
        for index, article in enumerate(articles):
            title = article.title.lower()
            content = article.content.lower()
            source = article.source.lower()
            platform = article.platform.lower()
            score = 0
            for term in terms:
                score += 4 if term in title else 0
                score += 2 if term in source or term in platform else 0
                score += min(content.count(term), 3)
            if score > 0:
                scored.append((score, -index, article))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored]

    def _select_multi_articles(
        self,
        valid_articles: list[Article],
        question: str,
        keywords: list[str],
        limit: int,
        requested_ids: list[str],
    ) -> list[Article]:
        if not valid_articles:
            return []
        if len(valid_articles) <= limit:
            return self._sort_by_publish_time(valid_articles)

        requested = [
            article
            for article in valid_articles
            if article.news_id is not None and str(article.news_id) in requested_ids
        ]
        remaining = [article for article in valid_articles if article not in requested]
        capacity = max(limit - len(requested), 0)
        ranked = self._rank_relevant_articles(remaining, question, keywords)
        representatives = ranked[:capacity]
        if len(representatives) < capacity:
            representatives.extend(
                article
                for article in remaining
                if article not in representatives
            )
            representatives = representatives[:capacity]
        return self._sort_by_publish_time(requested + representatives)

    def _classify(self, event: EventContext, question: str) -> str:
        requested_ids = self._extract_news_ids(question)
        if len(requested_ids) > 1:
            return "multi_specified_articles"
        if self._is_multi_article_question(question):
            return "multi_evidence"
        if any(word in question for word in ("升温", "降温", "趋势", "变热", "走向")):
            return "trend"
        if any(word in question for word in ("官方", "正式通报", "政府来源", "权威来源")):
            return "source_identity"
        has_news_id = re.search(r"news_id\s*[=:：]?\s*\d+", question, re.IGNORECASE)
        has_source = any(article.source and article.source in question for article in event.articles)
        if has_news_id or has_source or self._resolve_target_article(event.articles, question) is not None:
            return "article"
        if any(word in question for word in ("媒体", "来源", "哪些平台", "谁报道")):
            return "source"
        if any(word in question for word in ("风险", "危险", "风险点")):
            return "risk"
        if any(word in question for word in ("情绪", "情感", "正面", "负面", "中性")):
            return "sentiment"
        if any(word in question for word in ("发生了什么", "介绍", "概况", "概述", "什么事件")):
            return "summary"
        if any(word in question for word in ("天气", "幕后是谁", "谁策划", "一定会", "未来会不会")):
            return "out_of_scope"
        return "evidence"

    def _answer_summary(self, event: EventContext, question: str) -> QAResult:
        title = event.title.strip()
        summary = event.summary.strip()
        articles = self.select_relevant_articles(event, question) or self._sort_by_publish_time(
            event.articles[: self.top_k]
        )
        if not title and not summary and not articles:
            return self._answer_via_provider(event, question)
        return self._answer_with_provider(event, question, articles)

    def _answer_risk(self, event: EventContext, question: str) -> QAResult:
        analysis = event.analysis
        if not analysis.risk_level:
            return self._answer_via_provider(event, question)

        details = []
        if analysis.heat is not None:
            details.append(f"当前热度为{analysis.heat:g}")
        if analysis.stage:
            details.append(f"生命周期阶段为{analysis.stage}")
        if analysis.sentiment:
            sentiment_text = QAService._sentiment_values(analysis.sentiment)
            if sentiment_text:
                details.append(sentiment_text)
        if analysis.keywords:
            details.append("关键词包括" + "、".join(analysis.keywords))

        explanation = "；".join(details)
        if explanation:
            explanation = "可结合以下上游结果理解：" + explanation + "。"
        else:
            explanation = f"{INSUFFICIENT}，当前没有更多结构化指标可用于解释。"
        return QAResult(
            answer=(
                f"上游分析结果显示当前风险等级为“{analysis.risk_level}”，"
                f"5号仅对该结果进行解释，不重新计算或修改风险等级。{explanation}"
            ),
            confidence=0.8 if details else 0.5,
            limitations=[] if details else ["缺少风险解释所需的其他上游指标"],
        )

    def _answer_sentiment(self, event: EventContext, question: str) -> QAResult:
        sentiment = event.analysis.sentiment
        if sentiment is None:
            return self._answer_via_provider(event, question)
        values = QAService._sentiment_values(sentiment)
        if not values:
            return self._answer_via_provider(event, question)
        return QAResult(
            answer=f"上游情感分析结果显示：{values}。5号仅解释该结果，不重新计算情感值。",
            confidence=0.9,
        )

    def _answer_sources(self, event: EventContext, question: str) -> QAResult:
        if not event.articles:
            return self._answer_via_provider(event, question)

        records = []
        seen = set()
        for article in event.articles:
            source = article.source.strip() or "来源未标注"
            platform = article.platform.strip()
            key = (source, platform)
            if key in seen:
                continue
            seen.add(key)
            records.append(f"{source}（{platform}）" if platform else source)

        if not records or all(item == "来源未标注" for item in records):
            return self._answer_via_provider(event, question)
        return QAResult(
            answer="当前已提供的媒体或平台包括：" + "、".join(records) + "。",
            confidence=0.95,
            evidence_refs=QAService._refs(event.articles),
        )

    def _answer_source_identity(self, event: EventContext, question: str) -> QAResult:
        explicitly_official = [article for article in event.articles if QAService._is_official(article)]
        if explicitly_official:
            sources = []
            for article in explicitly_official:
                identity = article.source or article.title or "相关报道"
                if identity not in sources:
                    sources.append(identity)
            return QAResult(
                answer="当前输入将以下来源标记为官方来源："
                + "、".join(sources)
                + "。该表述仅依据输入中明确提供的来源身份信息。",
                confidence=0.95,
                evidence_refs=self._refs(explicitly_official),
            )

        has_identity_fields = any(
            article.is_official is not None or article.account_type or article.source_type
            for article in event.articles
        )
        if has_identity_fields:
            return QAResult(
                answer=(
                    "当前输入没有将这些来源明确标记为正式官方渠道；"
                    "现有材料也不足以判断是否存在其他官方信息。"
                ),
                confidence=0.8,
                limitations=["没有来源被显式标记为官方"],
            )
        return self._answer_via_provider(event, question)

    def _answer_article(self, event: EventContext, question: str) -> QAResult:
        if not event.articles:
            return self._answer_via_provider(event, question)

        article = self._resolve_target_article(event.articles, question)
        if article is None:
            return self._answer_via_provider(event, question)
        description = self._article_description(article)
        source = f"，来源为{article.source}" if article.source else ""
        return QAResult(
            answer=f"找到报道“{article.title or '标题未提供'}”{source}。{description}",
            confidence=0.9,
            evidence_refs=self._refs([article]),
        )

    @staticmethod
    def _answer_trend(event: EventContext) -> QAResult:
        heat_text = (
            f"当前上游热度值为{event.analysis.heat:g}，但它只是单个时点的数据。"
            if event.analysis.heat is not None
            else "当前连单个时点的热度值也未提供。"
        )
        article_note = ""
        if any(article.publish_time for article in event.articles):
            article_note = "文章发布时间只能描述已知报道顺序，不能等同于真实舆情热度趋势。"
        return QAResult(
            answer=(
                f"{heat_text}当前缺少连续时间序列，因此无法判断舆情是在升温还是降温。"
                f"{article_note}"
            ),
            confidence=0.95,
            limitations=["EventContext 不包含历史热度或完整趋势时间序列"],
        )

    def _answer_from_relevant_articles(self, event: EventContext, question: str) -> QAResult:
        articles = self.select_relevant_articles(event, question)
        if not articles:
            return self._answer_via_provider(event, question)

        return self._answer_with_provider(event, question, articles)

    def _answer_multi_article(self, event: EventContext, question: str) -> QAResult:
        articles = self.select_relevant_articles(event, question)
        if not articles:
            return self._answer_via_provider(event, question)
        return self._answer_with_provider(event, question, articles)

    def _answer_multiple_specified_articles(
        self,
        event: EventContext,
        question: str,
    ) -> QAResult:
        requested_ids = self._extract_news_ids(question)
        articles_by_id = {
            str(article.news_id): article
            for article in event.articles
            if article.news_id is not None and self._is_valid_article(article)
        }
        found = [articles_by_id[news_id] for news_id in requested_ids if news_id in articles_by_id]
        found = self._sort_by_publish_time(found)
        missing = [news_id for news_id in requested_ids if news_id not in articles_by_id]

        if not found:
            return self._answer_via_provider(event, question)

        prompt = build_qa_prompt(event, question, found, self.article_max_chars)
        provider_answer = self._generate_safely(prompt)
        article_sections = [self._specified_article_summary(article) for article in found]
        if self.provider.name == "fake":
            synthesis = "以上是当前材料中各指定文章分别提供的信息，未对文章说法作额外事实核验。"
        else:
            synthesis = provider_answer

        answer_parts = ["逐篇信息：", *article_sections, f"简短综合：{synthesis}"]
        if missing:
            answer_parts.append("部分用户指定的报道当前未包含在事件材料中。")
        return QAResult(
            answer="\n".join(answer_parts),
            confidence=0.7,
            evidence_refs=self._refs(found),
            limitations=["部分指定文章未找到"] if missing else [],
        )

    def _answer_with_provider(
        self,
        event: EventContext,
        question: str,
        articles: list[Article],
    ) -> QAResult:
        prompt = build_qa_prompt(event, question, articles, self.article_max_chars)
        provider_answer = self._generate_safely(prompt)
        if self.provider.name != "fake":
            return QAResult(
                answer=provider_answer,
                confidence=0.7,
                evidence_refs=self._refs(articles),
            )

        context = []
        if event.title or event.summary:
            context.append(
                "事件背景（不是独立新闻证据）："
                f"事件“{event.title or '标题未提供'}”：{event.summary or '摘要未提供'}"
            )
        evidence = [self._article_evidence_line(article) for article in articles]
        if evidence:
            context.append("选中文章证据：" + "；".join(evidence))
        conflict_note = ""
        if self._has_explicit_conflict(articles):
            conflict_note = "选中的多篇报道存在冲突，以下分别保留不同说法，不选择其中一种作为事实。"
        return QAResult(
            answer=f"{provider_answer} {conflict_note}" + " ".join(context),
            confidence=0.7,
            evidence_refs=self._refs(articles),
            limitations=["Fake Provider 仅整理关键词匹配到的证据，不代表真实模型综合分析"],
        )

    def _answer_via_provider(self, event: EventContext, question: str) -> QAResult:
        articles = self.select_relevant_articles(event, question)
        if not articles:
            valid_articles = [article for article in event.articles if self._is_valid_article(article)]
            articles = self._sort_by_publish_time(valid_articles[: self.top_k])
        return self._answer_with_provider(event, question, articles)

    @staticmethod
    def _resolve_target_article(articles: list[Article], question: str) -> Article | None:
        requested_ids = QAService._extract_news_ids(question)
        if len(requested_ids) == 1:
            target_id = requested_ids[0]
            for article in articles:
                if article.news_id is not None and str(article.news_id) == target_id:
                    return article
            return None

        source_matches = [article for article in articles if article.source and article.source in question]
        if len(source_matches) == 1:
            return source_matches[0]

        quoted_title = re.search(r"《([^》]{2,})》", question)
        if quoted_title:
            title_text = quoted_title.group(1)
            title_matches = [
                article
                for article in articles
                if title_text in article.title or (article.title and article.title in title_text)
            ]
            if len(title_matches) == 1:
                return title_matches[0]

        if "这篇" in question and len(articles) == 1:
            return articles[0]

        if any(cue in question for cue in ("那篇", "这篇", "题为", "标题")):
            distinctive_terms = QAService._title_terms(question)
            ranked = []
            for index, article in enumerate(articles):
                score = sum(1 for term in distinctive_terms if term in article.title)
                if score:
                    ranked.append((score, -index, article))
            if ranked:
                ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
                if len(ranked) == 1 or ranked[0][0] > ranked[1][0]:
                    return ranked[0][2]
        return None

    def _generate_safely(self, prompt: PromptBundle) -> str:
        try:
            response = self.provider.generate(prompt)
        except LLMProviderError:
            raise
        except (TimeoutError, ConnectionError) as exc:
            raise LLMProviderUnavailableError("LLM provider is unavailable") from exc
        except Exception as exc:
            raise LLMProviderError("LLM provider failed") from exc
        if not isinstance(response, str) or not response.strip():
            raise LLMProviderError("LLM provider returned an invalid response")
        return response.strip()

    @staticmethod
    def _title_terms(text: str) -> set[str]:
        chunks = re.findall(r"[\u4e00-\u9fff]+", text)
        generic = {"这篇报道", "那篇报道", "这篇新闻", "那篇新闻", "文章内容"}
        terms = set()
        for chunk in chunks:
            terms.update(chunk[index : index + 4] for index in range(len(chunk) - 3))
        return terms - generic

    @staticmethod
    def _question_terms(question: str, keywords: list[str]) -> set[str]:
        lowered = question.lower()
        terms = {term.lower() for term in re.findall(r"[a-zA-Z0-9_]{2,}", question)}
        terms.update(QAService._chinese_ngrams(question))
        terms.update(keyword.lower() for keyword in keywords if keyword and keyword.lower() in lowered)
        return terms

    @staticmethod
    def _chinese_ngrams(text: str) -> set[str]:
        chunks = re.findall(r"[\u4e00-\u9fff]+", text)
        stop_terms = {"这个", "事件", "什么", "如何", "一下", "当前", "有关", "哪些"}
        terms = set()
        for chunk in chunks:
            for size in (2, 3, 4):
                terms.update(chunk[index : index + size] for index in range(len(chunk) - size + 1))
        return terms - stop_terms

    @staticmethod
    def _article_description(article: Article) -> str:
        content = " ".join(article.content.split())
        if content:
            return f"“{article.title or '标题未提供'}”提到：{content[:240]}"
        if article.title:
            return f"已知报道标题为“{article.title}”，但正文内容未提供"
        return "该报道未提供标题和正文"

    @staticmethod
    def _article_evidence_line(article: Article) -> str:
        identity_parts = ["相关报道"]
        if article.source:
            identity_parts.append(f"来源为{article.source}")
        if article.title:
            identity_parts.append(f"标题为{article.title}")
        if article.publish_time:
            identity_parts.append(f"报道时间为{article.publish_time}")
        identity = "，".join(identity_parts)
        content = " ".join(article.content.split())
        if content:
            return f"{identity}：{content[:180]}"
        return f"{identity}：正文未提供"

    @staticmethod
    def _specified_article_summary(article: Article) -> str:
        title = f"标题“{article.title}”" if article.title else "标题未提供"
        source = f"来源“{article.source}”" if article.source else "来源未提供"
        publish_time = (
            f"报道时间 {article.publish_time}" if article.publish_time else "报道时间未提供"
        )
        content = " ".join(article.content.split())
        statement = content[:240] if content else "当前文章正文未提供具体内容"
        return (
            f"- {title}，{source}，{publish_time}。"
            f"该文章明确提及：{statement}"
        )

    @staticmethod
    def _sort_by_publish_time(articles: list[Article]) -> list[Article]:
        indexed = list(enumerate(articles))

        def sort_key(item: tuple[int, Article]) -> tuple[int, datetime, int]:
            index, article = item
            parsed = QAService._parse_publish_time(article.publish_time)
            if parsed is None:
                return (1, datetime.max, index)
            return (0, parsed, index)

        return [article for _, article in sorted(indexed, key=sort_key)]

    @staticmethod
    def _parse_publish_time(value: str | None) -> datetime | None:
        if not value or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    @staticmethod
    def _is_official(article: Article) -> bool:
        if article.is_official is True:
            return True
        account_type = (article.account_type or "").strip().lower()
        source_type = (article.source_type or "").strip().lower()
        return account_type in {"official", "官方", "政务"} or source_type in {
            "government",
            "official",
            "政府",
            "政务",
        }

    @staticmethod
    def _has_explicit_conflict(articles: list[Article]) -> bool:
        positive_markers = ("已经", "已确认", "已完成", "确认有")
        negative_markers = ("尚未", "暂无", "未确认", "仍未", "没有")
        contents = [" ".join(article.content.split()) for article in articles if article.content.strip()]
        for index, left in enumerate(contents):
            for right in contents[index + 1 :]:
                shared_terms = QAService._chinese_ngrams(left) & QAService._chinese_ngrams(right)
                if not shared_terms:
                    continue
                left_positive = any(marker in left for marker in positive_markers)
                left_negative = any(marker in left for marker in negative_markers)
                right_positive = any(marker in right for marker in positive_markers)
                right_negative = any(marker in right for marker in negative_markers)
                if (left_positive and right_negative) or (left_negative and right_positive):
                    return True
        return False

    @staticmethod
    def _is_multi_article_question(question: str) -> bool:
        return any(cue in question for cue in MULTI_ARTICLE_CUES)

    @staticmethod
    def _extract_news_ids(question: str) -> list[str]:
        matches = []
        pattern = r"news_id\s*[=:：]?\s*(\d+(?:\s*[,，、和及]\s*\d+)*)"
        for match in re.finditer(pattern, question, re.IGNORECASE):
            matches.extend(re.findall(r"\d+", match.group(1)))
        return list(dict.fromkeys(matches))

    @staticmethod
    def _is_valid_article(article: Article) -> bool:
        return article.news_id is not None or any(
            value.strip()
            for value in (article.title, article.content, article.source, article.url, article.platform)
        )

    @staticmethod
    def _finalize_result(result: QAResult) -> QAResult:
        answer = result.answer
        answer = re.sub(
            r"\b(?:articles?|news)\s*\[\s*\d+\s*\]\s*\.\s*",
            "",
            answer,
            flags=re.IGNORECASE,
        )
        answer = re.sub(
            r"\b(?:event|analysis|article|articles)\s*\.\s*",
            "",
            answer,
            flags=re.IGNORECASE,
        )
        answer = re.sub(
            r"[（(]\s*(?:(?:news|article|event)[_\s-]?id)\s*(?:[=:：#]\s*)?"
            r"(?:\[\s*)?\d+(?:\s*[,，、和及]\s*\d+)*(?:\s*\])?\s*[)）]",
            "",
            answer,
            flags=re.IGNORECASE,
        )
        answer = re.sub(
            r"\b(?:news|article)[_\s-]?id\s*(?:[=:：#]\s*)?"
            r"(?:\[\s*)?\d+(?:\s*[,，、和及]\s*\d+)*(?:\s*\])?",
            "相关报道",
            answer,
            flags=re.IGNORECASE,
        )
        answer = re.sub(
            r"\bevent[_\s-]?id\s*(?:[=:：#]\s*)?\d+",
            "当前事件",
            answer,
            flags=re.IGNORECASE,
        )
        answer = re.sub(
            r"is_official\s*[、,，]\s*account_type\s*[、,，]\s*source_type\s*字段均为空",
            "当前输入未提供足够的来源身份信息",
            answer,
            flags=re.IGNORECASE,
        )
        internal_names = {
            "news_id": "相关报道",
            "article_id": "相关报道",
            "event_id": "当前事件",
            "publish_time": "报道时间",
            "update_time_context_only": "上下文更新时间",
            "update_time": "更新时间",
            "event.summary": "事件摘要",
            "is_official": "来源身份信息",
            "account_type": "来源身份信息",
            "source_type": "来源身份信息",
            "provider_name": "模型服务配置",
            "article_max_chars": "文章长度限制",
            "top_k": "文章筛选数量",
            "PromptBundle": "提示信息",
            "EventContext": "事件上下文",
            "quoted_news_ids": "引用关系",
            "duplicate_group_id": "重复内容分组",
            "reference_urls": "参考链接",
        }
        for internal_name, natural_language in internal_names.items():
            answer = re.sub(re.escape(internal_name), natural_language, answer, flags=re.IGNORECASE)
        overstatements = (
            (r"官方(?:已经|已)?确认", "现有材料提及"),
            (r"已经证实|已证实", "现有材料提及"),
            (r"事实证明", "现有材料表述"),
            (r"已确认事实", "材料中明确提及的信息"),
            (r"当前唯一可确认的事实", "现有材料中较一致的说法"),
        )
        for pattern, replacement_text in overstatements:
            answer = re.sub(pattern, replacement_text, answer)
        answer = re.sub(
            r"(?<![A-Za-z0-9])[_A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+(?![A-Za-z0-9])",
            "相关信息",
            answer,
        )
        answer = re.sub(
            r"(?:相关报道\s*[、,，]\s*)+相关报道",
            "多篇相关报道",
            answer,
        )
        answer = re.sub(r"[（(]\s*[)）]", "", answer)
        answer = re.sub(r"\s+([，。；：！？])", r"\1", answer)
        answer = re.sub(r"[ \t]{2,}", " ", answer)
        return replace(result, answer=answer)

    @staticmethod
    def _sentiment_values(sentiment: Sentiment) -> str:
        values = []
        for label, value in (
            ("正面", sentiment.positive),
            ("中性", sentiment.neutral),
            ("负面", sentiment.negative),
        ):
            if value is not None:
                display = f"{value * 100:.1f}%" if 0 <= value <= 1 else f"{value:g}"
                values.append(f"{label}{display}")
        return "、".join(values)

    @staticmethod
    def _refs(articles: list[Article]) -> list[str]:
        refs = []
        for article in articles:
            if article.news_id is not None:
                refs.append(str(article.news_id))
            elif article.url:
                refs.append(article.url)
        return refs


@lru_cache
def get_qa_service() -> QAService:
    return QAService(
        provider=create_llm_provider(settings.llm_provider, config=settings),
        top_k=settings.qa_top_k,
        article_max_chars=settings.article_max_chars,
    )
