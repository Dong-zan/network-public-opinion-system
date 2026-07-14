import re
from abc import ABC, abstractmethod

from app.schemas.event import Article
from app.schemas.verification import LanguageAssessment, LanguageRiskFlag


class LanguageRiskAnalyzer(ABC):
    @abstractmethod
    def analyze(self, article: Article) -> LanguageAssessment:
        raise NotImplementedError


class DeterministicLanguageRiskAnalyzer(LanguageRiskAnalyzer):
    """Rule-only wording risk detector; it deliberately makes no truth judgment."""

    _rules = (
        ("absolute_claim", 3, r"(?:原因|真相|事故原因).{0,8}(?:百分百|100%).{0,8}(?:确定|证实|确认)", "文本使用了高度确定的结论性表述。"),
        ("absolute_claim", 3, r"一定造成[^。！？；]{0,12}(?:伤亡|死亡|受伤)", "文本使用了未保留条件的伤亡断言。"),
        ("absolute_claim", 3, r"毫无疑问[^。！？；]{0,20}(?:人为|事故|原因)", "文本使用了未保留条件的原因判断。"),
        ("sensational_language", 2, r"惊天内幕|爆炸性内幕|震惊全国", "文本使用了煽动性或吸引注意的措辞。"),
        ("anonymous_attribution", 2, r"据不愿透露姓名的[^。！？；]{0,20}(?:称|表示)", "文本引用了无法识别的匿名消息来源。"),
        ("emotional_manipulation", 2, r"令人发指|触目惊心|天理难容", "文本使用了强烈情绪化措辞。"),
        ("conspiracy_claim", 3, r"官方肯定在隐瞒真相|[^。！？；]{0,12}(?:阴谋|掩盖真相)", "文本包含缺少可核验依据的阴谋式指控。"),
    )
    _absolute_context_exceptions = ("工程完成率", "电池电量", "统计覆盖率")

    def analyze(self, article: Article) -> LanguageAssessment:
        flags = []
        for text in (article.title, article.content):
            for risk_type, severity, pattern, explanation in self._rules:
                for match in re.finditer(pattern, text):
                    quote = match.group(0)
                    if risk_type == "absolute_claim" and self._is_measurement_context(text, match.start()):
                        continue
                    flags.append(
                        LanguageRiskFlag(
                            type=risk_type,
                            severity=severity,
                            quote=quote,
                            explanation=explanation,
                        )
                    )
        flags = self._stable_flags(flags)
        score = self._risk_score(flags)
        level = "low" if not flags else "high" if score >= 50 else "medium"
        return LanguageAssessment(risk_level=level, risk_score=score, flags=flags)

    def _is_measurement_context(self, text: str, index: int) -> bool:
        context = text[max(0, index - 16) : index + 16]
        return any(marker in context for marker in self._absolute_context_exceptions)

    @staticmethod
    def _risk_score(flags: list[LanguageRiskFlag]) -> float:
        per_type = {}
        for flag in flags:
            per_type[flag.type] = max(per_type.get(flag.type, 0), flag.severity)
        return round(min(100.0, sum({1: 10.0, 2: 20.0, 3: 30.0}[severity] for severity in per_type.values())), 1)

    @staticmethod
    def _stable_flags(flags: list[LanguageRiskFlag]) -> list[LanguageRiskFlag]:
        unique = {}
        for flag in flags:
            unique.setdefault((flag.type, flag.quote), flag)
        return sorted(unique.values(), key=lambda item: (item.type, -item.severity, item.quote))
