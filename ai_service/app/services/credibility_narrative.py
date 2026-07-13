from app.schemas.verification import LanguageAssessment, SourceAssessment, VerificationResponse


class CredibilityNarrativeBuilder:
    def build(
        self,
        verification: VerificationResponse,
        source: SourceAssessment,
        language: LanguageAssessment,
    ) -> tuple[str, list[str]]:
        sentences = [self._evidence_sentence(verification.overall_verdict)]
        sentences.append(self._source_sentence(source))
        sentences.append(self._language_sentence(language))
        if verification.overall_verdict in {"supported", "contradicted", "conflicting"}:
            sentences.append("该结论仅基于当前输入材料，后续正式信息可能改变判断。")
        else:
            sentences.append("证据不足不等于文章已经被证明为虚假。")
        factors = self._factors(verification, source, language)
        return "".join(sentences), factors

    @staticmethod
    def _evidence_sentence(verdict: str) -> str:
        messages = {
            "supported": "目标文章的主要可核验事实得到多个独立来源支持。",
            "contradicted": "目标文章的部分核心主张与多个独立来源的明确表述冲突，当前反驳证据较强。",
            "conflicting": "当前输入材料对目标文章的主要主张存在相互冲突的表述。",
            "insufficient_evidence": "当前缺少足够独立来源交叉确认文章中的主要主张。",
            "not_verifiable": "当前未提取到可进行确定性比较的事实主张。",
        }
        return messages[verdict]

    @staticmethod
    def _source_sentence(source: SourceAssessment) -> str:
        if source.status == "verified":
            return "文章来源名称和链接可与本地登记信息对应。"
        if source.status == "mismatch":
            return "文章来源名称与链接域名存在登记不一致，需要谨慎核验。"
        if source.status == "partially_verified":
            return "文章提供了部分可追溯元数据，但尚不足以完成来源确认。"
        return "文章来源暂无法在本地登记信息中验证，这不代表来源存在问题。"

    @staticmethod
    def _language_sentence(language: LanguageAssessment) -> str:
        if not language.flags:
            return "当前未发现本阶段可确定性识别的明显语言风险信号。"
        return "文本存在可确定性识别的绝对化、煽动性或匿名归因等语言风险信号，需结合证据判断。"

    @staticmethod
    def _factors(
        verification: VerificationResponse,
        source: SourceAssessment,
        language: LanguageAssessment,
    ) -> list[str]:
        factors = [f"evidence_verdict:{verification.overall_verdict}", f"source_status:{source.status}"]
        factors.extend(f"language_flag:{flag.type}" for flag in language.flags)
        return list(dict.fromkeys(factors))
