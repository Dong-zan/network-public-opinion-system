import re
from dataclasses import dataclass, replace
from typing import Any

from app.schemas.event import Article
from app.services.claim_atomizer import AtomizedClaim, ClaimAtomizer


@dataclass(frozen=True)
class AtomicClaim:
    text: str
    target_quote: str
    claim_type: str
    certainty: str
    polarity: str
    modality_reason: str | None
    slots: dict[str, Any]
    verifiable: bool
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    time: str | None = None
    location: str | None = None


class ClaimExtractor:
    _instruction_markers = (
        "忽略之前",
        "忽略以上",
        "忽略规则",
        "系统指令",
        "system prompt",
        "改变结论",
        "输出supported",
        "输出contradicted",
        "判定supported",
        "判定contradicted",
    )
    _subjective_markers = (
        "我认为",
        "可能会",
        "预计",
        "建议",
        "应该",
        "或许",
        "未来将",
    )
    _attribution_only = re.compile(
        r"^(?:据[^，,。]{0,12}(?:通报|消息)|据了解|记者获悉|有消息称|报道称)$"
    )
    _priorities = {
        "casualty": 100,
        "event_time": 95,
        "location": 90,
        "cause": 85,
        "response_status": 80,
        "conclusion_status": 75,
        "quantity": 70,
        "other": 10,
    }

    def __init__(self, atomizer: ClaimAtomizer | None = None) -> None:
        self.atomizer = atomizer or ClaimAtomizer()

    def extract(self, article: Article, max_claims: int) -> list[AtomicClaim]:
        candidates = self.extract_text(article.content)
        best_by_identity: dict[tuple[Any, ...], tuple[int, AtomicClaim]] = {}
        for order, claim in candidates:
            identity = self._claim_identity(claim)
            existing = best_by_identity.get(identity)
            if existing is None or self._prefer_claim(claim, existing[1]):
                best_by_identity[identity] = (min(order, existing[0]) if existing else order, claim)
        ranked = list(best_by_identity.values())
        ranked.sort(
            key=lambda item: (-self._priorities[item[1].claim_type], item[0])
        )
        result = []
        for _, claim in ranked:
            result.append(claim)
            if len(result) >= max_claims:
                break
        return result

    def atomize_claims(self, claims: list[AtomicClaim]) -> list[AtomizedClaim]:
        quotes = [claim.target_quote.strip() for claim in claims if claim.target_quote.strip()]
        parent_claims = []
        for quote in quotes:
            if quote in parent_claims:
                continue
            if any(quote != candidate and quote in candidate for candidate in quotes):
                continue
            parent_claims.append(quote)
        return self.atomizer.atomize_many(parent_claims)

    def normalize_atomized_claim(self, item: AtomizedClaim) -> AtomicClaim:
        extracted = self.extract(Article(content=item.text), 1)
        claim = extracted[0] if extracted else AtomicClaim(
            text=item.text,
            target_quote=item.text,
            claim_type="other",
            certainty="asserted",
            polarity="affirmative",
            modality_reason=None,
            slots={},
            verifiable=True,
        )
        return self._apply_atomized_structure(claim, item)

    def normalize_atomized_evidence(self, item: AtomizedClaim) -> list[AtomicClaim]:
        extracted = [claim for _, claim in self.extract_text(item.text)]
        if not extracted:
            return [self.normalize_atomized_claim(item)]
        return [
            self._apply_atomized_structure(claim, item)
            for claim in extracted
        ]

    @staticmethod
    def _apply_atomized_structure(
        claim: AtomicClaim,
        item: AtomizedClaim,
    ) -> AtomicClaim:
        generic_claim = claim.claim_type == "other"
        return replace(
            claim,
            subject=item.subject,
            predicate=item.predicate,
            object=item.object,
            time=item.time,
            location=item.location,
            polarity=(item.polarity or claim.polarity) if generic_claim else claim.polarity,
            certainty=(
                (item.certainty or claim.certainty)
                if generic_claim
                else claim.certainty
            ),
        )

    def extract_text(self, content: str) -> list[tuple[int, AtomicClaim]]:
        candidates = []
        order = 0
        for sentence_match in re.finditer(r"[^。！？；;\n]+[。！？；;]?", content):
            sentence = sentence_match.group(0)
            sentence_body = sentence.rstrip("。！？；;").strip()
            clauses = [
                clause.group(0).strip()
                for clause in re.finditer(r"[^，,]+", sentence_body)
                if clause.group(0).strip() != sentence_body
            ]
            if clauses and self._has_scoped_modality(sentence_body):
                spans = self._scoped_spans(clauses)
            elif clauses and self._is_reference_time_prefix(clauses[0]):
                spans = [sentence_body]
            else:
                spans = [sentence_body, *clauses]
            for quote in spans:
                normalized = " ".join(quote.split()).strip(" ：:")
                if (
                    self._is_reference_time_prefix(normalized)
                    or not self._eligible(normalized)
                ):
                    continue
                for claim in self._build_claims(normalized, quote.strip()):
                    candidates.append((order, claim))
                    order += 1
        return candidates

    def _build_claims(self, text: str, target_quote: str) -> list[AtomicClaim]:
        certainty = self._certainty(text)
        polarity = self._polarity(text)
        modality_reason = self._modality_reason(text)
        verifiable = not any(marker in text for marker in self._subjective_markers)
        time_slots = self._event_time_slots(text)
        reference_time_slots = self._reference_time_slots(text)
        typed: list[tuple[str, dict[str, Any]]] = []

        casualty_matches = list(re.finditer(
            r"(\d+)\s*(人|名)(?:人员)?\s*(受伤|死亡|遇难|失踪|住院|入院|送医|伤亡)",
            text,
        ))
        for casualty in casualty_matches:
            casualty_types = {
                "受伤": "injured",
                "死亡": "dead",
                "遇难": "dead",
                "失踪": "missing",
                "住院": "hospitalized",
                "入院": "hospitalized",
                "送医": "hospitalized",
                "伤亡": "generic_casualty",
            }
            slots: dict[str, Any] = {
                "count": int(casualty.group(1)),
                "unit": "人",
                "casualty_type": casualty_types[casualty.group(3)],
            }
            if reference_time_slots:
                slots["reference_time"] = reference_time_slots
            typed.append(("casualty", slots))

        compact_patterns = (
            (r"(\d+)\s*死", "dead"),
            (r"(\d+)\s*伤", "injured"),
            (r"(\d+)\s*(?:失联|失踪)", "missing"),
        )
        occupied = {
            (int(match.group(1)), {
                "受伤": "injured",
                "死亡": "dead",
                "遇难": "dead",
                "失踪": "missing",
                "住院": "hospitalized",
                "入院": "hospitalized",
                "送医": "hospitalized",
                "伤亡": "generic_casualty",
            }[match.group(3)])
            for match in casualty_matches
        }
        for pattern, casualty_type in compact_patterns:
            for match in re.finditer(pattern, text):
                identity = (int(match.group(1)), casualty_type)
                if identity in occupied:
                    continue
                slots = {
                    "count": identity[0],
                    "unit": "人",
                    "casualty_type": casualty_type,
                }
                if reference_time_slots:
                    slots["reference_time"] = reference_time_slots
                typed.append(("casualty", slots))
                occupied.add(identity)

        zero_casualty = re.search(
            r"(?:未造成人员伤亡|无人员伤亡|暂无人员伤亡|尚无人员伤亡|零伤亡|"
            r"未发现人员伤亡|暂未发现人员伤亡|尚未发现人员伤亡|未发现伤亡|暂未发现伤亡)",
            text,
        )
        if zero_casualty:
            observational_zero = any(
                marker in zero_casualty.group(0)
                for marker in ("暂无", "尚无", "未发现")
            )
            if observational_zero:
                certainty = "unconfirmed"
                modality_reason = "claim_modality_unconfirmed"
            slots = {"count": 0, "unit": "人", "casualty_type": "generic_casualty"}
            if reference_time_slots:
                slots["reference_time"] = reference_time_slots
            typed.append(("casualty", slots))
            polarity = "affirmative"

        if time_slots:
            typed.append(("event_time", time_slots))

        location = self._location_slots(text)
        if location:
            typed.append(("location", location))

        if "原因" in text and self._contains_unconfirmed(text):
            typed.append(("cause", {"cause": None, "status": "under_investigation"}))
        else:
            cause = self._specific_cause(text)
            if cause:
                typed.append(("cause", {"cause": cause}))

        response_status = self._response_status(text)
        if response_status:
            slots = {"action": "rescue", "status": response_status}
            if reference_time_slots:
                slots["reference_time"] = reference_time_slots
            typed.append(("response_status", slots))

        conclusion_status = self._conclusion_status(text)
        if conclusion_status:
            slots = {"status": conclusion_status}
            if reference_time_slots:
                slots["reference_time"] = reference_time_slots
            typed.append(("conclusion_status", slots))

        quantity = self._quantity_slots(text, bool(casualty_matches or zero_casualty))
        if quantity:
            typed.append(("quantity", quantity))
        if not typed:
            typed.append(("other", {}))

        return [
            AtomicClaim(
                text=text,
                target_quote=target_quote,
                claim_type=claim_type,
                certainty=certainty,
                polarity=polarity,
                modality_reason=modality_reason,
                slots=slots,
                verifiable=verifiable,
            )
            for claim_type, slots in typed
        ]

    @staticmethod
    def _event_time_slots(text: str) -> dict[str, str]:
        segments = [
            segment.strip()
            for segment in re.split(r"[，,；;]", text)
            if segment.strip()
        ]
        for index, segment in enumerate(segments):
            if not re.search(r"(?:发生|事发)", segment):
                continue
            local_time = ClaimExtractor._time_components(segment)
            if local_time:
                return local_time
            if index > 0 and ClaimExtractor._is_time_prefix(segments[index - 1]):
                return ClaimExtractor._time_components(segments[index - 1])
        return {}

    @staticmethod
    def _is_time_prefix(text: str) -> bool:
        return not text.startswith("截至") and ClaimExtractor._is_reference_time_prefix(text)

    @staticmethod
    def _is_reference_time_prefix(text: str) -> bool:
        components = ClaimExtractor._time_components(text)
        if not components:
            return False
        remainder = re.sub(
            r"(?:\d{4}年)?\d{1,2}月\d{1,2}日|\d{4}-\d{1,2}-\d{1,2}|"
            r"(?:凌晨|早上|上午|中午|下午|晚上)?\s*\d{1,2}(?:时|点)(?:\d{1,2}分)?|"
            r"\d{1,2}:\d{2}|截至|当日|当天|今日",
            "",
            text,
        )
        return not remainder.strip()

    @staticmethod
    def _reference_time_slots(text: str) -> dict[str, str]:
        return ClaimExtractor._time_components(text)

    @staticmethod
    def _time_components(text: str) -> dict[str, str]:
        slots: dict[str, str] = {}
        full_date = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
        iso_date = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
        month_day = re.search(r"(?<!\d)(\d{1,2})月(\d{1,2})日", text)
        date_match = full_date or iso_date
        if date_match:
            slots["event_date"] = (
                f"{int(date_match.group(1)):04d}-{int(date_match.group(2)):02d}-"
                f"{int(date_match.group(3)):02d}"
            )
        elif month_day:
            slots["event_date"] = (
                f"{int(month_day.group(1)):02d}-{int(month_day.group(2)):02d}"
            )

        clock = re.search(
            r"(?:(凌晨|早上|上午|中午|下午|晚上)\s*)?(\d{1,2})(?:时|点)(?:(\d{1,2})分)?",
            text,
        )
        colon = re.search(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)", text)
        if clock:
            normalized_time = ClaimExtractor._normalize_clock(
                clock.group(1),
                int(clock.group(2)),
                int(clock.group(3) or 0),
            )
            if normalized_time:
                slots["event_time"] = normalized_time
        elif colon:
            hour = int(colon.group(1))
            minute = int(colon.group(2))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                slots["event_time"] = f"{hour:02d}:{minute:02d}"
        if "event_date" in slots and "event_time" in slots:
            slots["event_datetime"] = f"{slots['event_date']}T{slots['event_time']}"
        return slots

    @staticmethod
    def _normalize_clock(period: str | None, hour: int, minute: int) -> str | None:
        if not 0 <= minute <= 59:
            return None
        if period is None:
            normalized_hour = hour
        elif not 0 <= hour <= 12:
            return None
        elif period in {"凌晨", "早上", "上午"}:
            normalized_hour = 0 if hour == 12 else hour
        elif period == "中午":
            if hour == 12:
                normalized_hour = 12
            elif hour == 1:
                normalized_hour = 13
            elif hour == 11:
                normalized_hour = 11
            else:
                return None
        elif period == "下午":
            normalized_hour = hour if hour == 12 else hour + 12
        else:
            normalized_hour = 0 if hour == 12 else hour + 12
        if not 0 <= normalized_hour <= 23:
            return None
        return f"{normalized_hour:02d}:{minute:02d}"

    @staticmethod
    def _location_slots(text: str) -> dict[str, str]:
        match = re.search(
            r"(?:事故发生地点|事故地点|事发地点|事发地)\s*(?:为|是|位于)\s*"
            r"([\u4e00-\u9fff]{2,30}?)(?=，|。|造成|$)",
            text,
        )
        if not match:
            match = re.search(
                r"(?:发生在|事发于|位于)\s*([\u4e00-\u9fff]{2,20}?)"
                r"(?=，|。|造成|发生|系|(?:的)?(?:消息|说法)|$)",
                text,
            )
        if not match:
            match = re.search(
                r"(?:^|[，,])\s*([\u4e00-\u9fff]{2,20}?)(?:发生|突发)(?:事故|事件)",
                text,
            )
        if not match:
            match = re.search(
                r"(?:并非|不是|并不|没有)?在\s*([\u4e00-\u9fff]{2,20}?)发生",
                text,
            )
        if not match:
            return {}
        name = match.group(1).strip()
        slots = {"normalized_name": name}
        if name.endswith("路"):
            slots["detail"] = name
            return slots
        administrative = ClaimExtractor._administrative_location(name)
        slots.update(administrative)
        if not administrative:
            slots["detail"] = name
        return slots

    @staticmethod
    def _administrative_location(name: str) -> dict[str, str]:
        slots: dict[str, str] = {}
        remainder = name
        province_match = re.match(r"(.+?(?:省|自治区))", remainder)
        if province_match:
            province_name = province_match.group(1)
            slots["province"] = re.sub(r"(?:省|自治区)$", "", province_name)
            remainder = remainder[province_match.end() :]

        municipality = next(
            (value for value in ("北京", "上海", "天津", "重庆") if remainder.startswith(value)),
            None,
        )
        if municipality:
            slots["city"] = municipality
            slots["province_or_city"] = municipality
            remainder = remainder[len(municipality) :]
            if remainder.startswith("市"):
                remainder = remainder[1:]
        else:
            city_match = re.match(r"(.+?)市", remainder)
            if city_match:
                city = city_match.group(1)
                slots["city"] = city
                slots["province_or_city"] = city
                remainder = remainder[city_match.end() :]
            elif not slots and re.fullmatch(r"[\u4e00-\u9fff]{2,8}", remainder):
                slots["city"] = remainder
                slots["province_or_city"] = remainder
                remainder = ""

        district_match = re.match(r"(.+?(?:区|县))", remainder)
        if district_match:
            slots["district"] = district_match.group(1)
            remainder = remainder[district_match.end() :]
        if remainder:
            slots["detail"] = remainder
        return slots

    @staticmethod
    def _specific_cause(text: str) -> str | None:
        patterns = (
            r"(?:并非由于|不是由于|由于|因)\s*(.+?)(?:导致|引发)",
            r"(?:不是|并非)?\s*([\u4e00-\u9fffA-Za-z0-9]{2,20}?)(?:导致|引发)(?:了)?(?:事故|事件)",
            r"原因(?:不是|并非|是|为)\s*([^，。；;]{2,30})",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def _response_status(text: str) -> str | None:
        if not any(marker in text for marker in ("救援", "搜救")):
            return None
        status_markers = (
            ("not_started", ("尚未展开", "还未开始", "未启动", "没有启动", "没有展开")),
            ("completed", ("已经结束", "已结束", "已经完成", "已完成")),
            ("suspended", ("已经暂停", "已暂停", "中止", "暂停救援")),
            ("ongoing", ("正在进行", "仍在进行", "持续进行", "正在展开")),
            ("started", ("已经展开", "已展开", "已经启动", "已启动")),
        )
        for status, markers in status_markers:
            if any(marker in text for marker in markers):
                return status
        return "unknown"

    @staticmethod
    def _conclusion_status(text: str) -> str | None:
        if not any(marker in text for marker in ("调查结论", "结论", "调查")):
            return None
        if any(
            marker in text
            for marker in (
                "仍在调查",
                "调查仍在进行",
                "调查正在进行",
                "尚无最终",
                "暂无最终",
                "尚未形成",
            )
        ):
            return "under_investigation"
        if any(marker in text for marker in ("初步结论", "初步调查")):
            return "preliminary"
        if any(marker in text for marker in ("最终结论", "最终调查结论", "结论已经形成")):
            return "final"
        if any(marker in text for marker in ("否认", "不属实")):
            return "denied"
        return "unknown"

    @staticmethod
    def _quantity_slots(text: str, has_casualty: bool) -> dict[str, Any]:
        match = re.search(r"(\d+(?:\.\d+)?)\s*(万元|元|辆|起|次|人|名|%)", text)
        if not match or (has_casualty and match.group(2) in {"人", "名"}):
            return {}
        if any(marker in text for marker in ("损失", "经济损失", "财产损失")):
            measure_type = "economic_loss"
        elif any(marker in text for marker in ("捐款", "捐赠", "募捐")):
            measure_type = "donation_amount"
        elif any(marker in text for marker in ("车辆", "汽车", "货车", "客车")):
            measure_type = "vehicle_count"
        elif any(marker in text for marker in ("事故", "事件", "案件")) and match.group(2) in {"起", "次"}:
            measure_type = "incident_count"
        else:
            measure_type = "generic_quantity"
        prefix = text[max(0, match.start() - 12) : match.start()].strip()
        return {
            "value": float(match.group(1)),
            "unit": "人" if match.group(2) == "名" else match.group(2),
            "measure_type": measure_type,
            "subject_anchor": prefix,
        }

    @staticmethod
    def _certainty(text: str) -> str:
        if ClaimExtractor._contains_unconfirmed(text) or re.search(
            r"(?:网传|据传|有消息称|据称|疑似|可能|或有|尚待核实)", text
        ):
            return "unconfirmed"
        if any(marker in text for marker in ("已确认", "已经确认", "证实", "确认")):
            return "confirmed"
        return "asserted"

    @staticmethod
    def _polarity(text: str) -> str:
        if ClaimExtractor._explicit_refutation(text):
            return "negative"
        negative_patterns = (
            r"(?:未|没有|并未)造成\s*\d+\s*(?:人|名)",
            r"(?:未|并未|并非|没有)发生(?:在|于)?",
            r"(?:不是|并非)(?:由于)?[^，。；;]{1,30}(?:导致|引发)",
            r"(?:尚未展开|还未开始|未启动|没有启动|没有展开)",
            r"(?:并非|不是|并不|没有)在[^，。；;]{1,30}发生",
        )
        if any(re.search(pattern, text) for pattern in negative_patterns):
            return "negative"
        if ClaimExtractor._contains_unconfirmed(text) or re.search(
            r"(?:网传|据传|有消息称|据称|疑似|可能|或有|尚待核实)", text
        ):
            return "unknown"
        return "affirmative"

    @staticmethod
    def _modality_reason(text: str) -> str | None:
        if ClaimExtractor._explicit_refutation(text):
            return "claim_explicitly_refuted"
        if re.search(r"(?:网传|据传|有消息称|据称)", text):
            return "claim_reported_as_rumor"
        if re.search(r"(?:疑似|可能|或有|尚待核实|未经证实|尚未确认|暂未确认)", text):
            return "claim_modality_unconfirmed"
        return None

    @staticmethod
    def _has_scoped_modality(text: str) -> bool:
        return ClaimExtractor._explicit_refutation(text) or bool(
            re.search(r"(?:网传|据传|有消息称|据称|疑似|可能|或有|尚待核实)", text)
        )

    @staticmethod
    def _explicit_refutation(text: str) -> bool:
        return bool(
            re.search(
                r"(?:系|为)(?:谣言|不实(?:信息)?|虚假消息)|"
                r"(?:消息|说法|传言)(?:系)?(?:谣言|不实|不属实)|"
                r"经核实[^，。；;]{0,50}(?:不属实|系谣言|系不实)|"
                r"并无此事",
                text,
            )
        )

    @staticmethod
    def _scoped_spans(clauses: list[str]) -> list[str]:
        spans = []
        prefixes = []
        for clause in clauses:
            if re.fullmatch(r"(?:网传|据传|有消息称|据称)", clause) or (
                ClaimExtractor._is_reference_time_prefix(clause)
            ):
                prefixes.append(clause)
                continue
            if prefixes:
                spans.append("，".join([*prefixes, clause]))
                prefixes.clear()
            else:
                spans.append(clause)
        spans.extend(prefixes)
        return spans

    @staticmethod
    def _contains_unconfirmed(text: str) -> bool:
        return bool(
            re.search(
                r"(?:仍在调查|尚在调查|正在调查|尚未确认|暂未确认|未经证实|暂无(?:最终)?结论|尚无最终调查结论)",
                text,
            )
        )

    @classmethod
    def _eligible(cls, text: str) -> bool:
        return bool(
            len(text) >= 4
            and not cls.contains_instruction(text)
            and not cls._attribution_only.fullmatch(text)
        )

    @staticmethod
    def _claim_identity(claim: AtomicClaim) -> tuple[Any, ...]:
        slots = tuple(sorted((key, str(value)) for key, value in claim.slots.items()))
        if claim.claim_type != "other" and slots:
            return (
                claim.claim_type,
                claim.certainty,
                claim.polarity,
                claim.modality_reason,
                slots,
            )
        return (
            claim.claim_type,
            claim.certainty,
            claim.polarity,
            claim.modality_reason,
            claim.text,
        )

    @staticmethod
    def _prefer_claim(candidate: AtomicClaim, existing: AtomicClaim) -> bool:
        if len(candidate.slots) != len(existing.slots):
            return len(candidate.slots) > len(existing.slots)
        return len(candidate.target_quote) < len(existing.target_quote)

    @classmethod
    def contains_instruction(cls, text: str) -> bool:
        return any(marker.lower() in text.lower() for marker in cls._instruction_markers)
