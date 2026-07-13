import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.services.claim_extractor import AtomicClaim, ClaimExtractor
from app.services.event_evolution_analyzer import EventEvolutionAnalyzer


@dataclass(frozen=True)
class StanceDecision:
    stance: str
    reason_code: str
    relevance_score: float


class StanceClassifier:
    def __init__(self, extractor: ClaimExtractor | None = None) -> None:
        self.extractor = extractor or ClaimExtractor()

    def classify(
        self,
        claim: AtomicClaim | str,
        evidence: str,
        *,
        target_publish_time: str | None = None,
        evidence_publish_time: str | None = None,
    ) -> StanceDecision:
        target = self._as_claim(claim)
        evidence_claims = [item for _, item in self.extractor.extract_text(evidence)]
        if not evidence_claims:
            return StanceDecision("irrelevant", "no_comparable_fact", 0.0)
        ranked = sorted(
            (
                (
                    candidate.claim_type == target.claim_type,
                    self._comparability(target, candidate),
                    self._relevance(target, candidate),
                    index,
                    candidate,
                )
                for index, candidate in enumerate(evidence_claims)
            ),
            key=lambda item: (-int(item[0]), -item[1], -item[2], item[3]),
        )
        _, _, relevance, _, candidate = ranked[0]
        if relevance < 0.2:
            return StanceDecision("irrelevant", "low_relevance", round(relevance, 3))
        if candidate.claim_type != target.claim_type:
            return StanceDecision("related", "related_but_not_comparable", round(relevance, 3))
        stance, reason = self._compare_same_type(
            target,
            candidate,
            target_publish_time=target_publish_time,
            evidence_publish_time=evidence_publish_time,
        )
        return StanceDecision(stance, reason, round(relevance, 3))

    def relevance(self, claim: AtomicClaim, evidence: str) -> float:
        candidates = [item for _, item in self.extractor.extract_text(evidence)]
        return max(
            (self._relevance(claim, candidate) for candidate in candidates),
            default=0.0,
        )

    def compare_claims(
        self,
        target: AtomicClaim,
        evidence: AtomicClaim,
        *,
        target_publish_time: str | None = None,
        evidence_publish_time: str | None = None,
    ) -> StanceDecision:
        relevance = self._relevance(target, evidence)
        if target.claim_type != evidence.claim_type:
            return StanceDecision(
                "related",
                "related_but_not_comparable",
                round(relevance, 3),
            )
        stance, reason = self._compare_same_type(
            target,
            evidence,
            target_publish_time=target_publish_time,
            evidence_publish_time=evidence_publish_time,
        )
        return StanceDecision(stance, reason, round(relevance, 3))

    @staticmethod
    def _compare_same_type(
        target: AtomicClaim,
        evidence: AtomicClaim,
        *,
        target_publish_time: str | None,
        evidence_publish_time: str | None,
    ) -> tuple[str, str]:
        time_relation = StanceClassifier._time_relation(
            target,
            evidence,
            target_publish_time,
            evidence_publish_time,
        )
        observational_zero_pair = (
            StanceClassifier._is_observational_zero_casualty(target)
            or StanceClassifier._is_observational_zero_casualty(evidence)
        )
        zero_positive_pair = StanceClassifier._zero_positive_casualty_pair(
            target,
            evidence,
        )
        if observational_zero_pair and zero_positive_pair:
            if time_relation == "same_time":
                return "contradicts", "casualty_count_conflict"
            temporal = StanceClassifier._dynamic_temporal_decision(
                target,
                evidence,
                time_relation,
            )
            if temporal:
                return temporal
        uncertainty = None
        if not (
            target.claim_type == "cause"
            and (target.slots.get("cause") is None or evidence.slots.get("cause") is None)
        ):
            uncertainty = StanceClassifier._uncertainty_decision(target, evidence)
        if uncertainty:
            return uncertainty
        temporal = StanceClassifier._dynamic_temporal_decision(
            target,
            evidence,
            time_relation,
        )
        if temporal:
            return temporal
        if target.claim_type == "casualty":
            return StanceClassifier._compare_casualty(target, evidence)
        if target.claim_type == "location":
            return StanceClassifier._compare_location(target, evidence)
        if target.claim_type == "event_time":
            return StanceClassifier._compare_event_time(target, evidence)
        if target.claim_type == "cause":
            return StanceClassifier._compare_cause(target, evidence)
        if target.claim_type == "response_status":
            return StanceClassifier._compare_status(target, evidence, "response_status")
        if target.claim_type == "conclusion_status":
            return StanceClassifier._compare_status(target, evidence, "conclusion_status")
        if target.claim_type == "quantity":
            return StanceClassifier._compare_quantity(target, evidence)
        return "related", "unstructured_claim_not_deterministically_comparable"

    @staticmethod
    def _compare_casualty(target: AtomicClaim, evidence: AtomicClaim) -> tuple[str, str]:
        polarity = StanceClassifier._polarity_decision(
            target,
            evidence,
            same_proposition=(
                target.slots.get("casualty_type") == evidence.slots.get("casualty_type")
                and target.slots.get("count") == evidence.slots.get("count")
            ),
        )
        if polarity:
            return polarity
        if StanceClassifier._uncertain_pair(target, evidence):
            return "related", "casualty_status_not_confirmed"
        if target.slots.get("casualty_type") != evidence.slots.get("casualty_type"):
            return "contradicts", "casualty_type_conflict"
        if target.slots.get("count") != evidence.slots.get("count"):
            return "contradicts", "casualty_count_conflict"
        return "supports", "same_casualty_type_and_count"

    @staticmethod
    def _compare_location(target: AtomicClaim, evidence: AtomicClaim) -> tuple[str, str]:
        relation = StanceClassifier._location_relation(target.slots, evidence.slots)
        polarity = StanceClassifier._polarity_decision(
            target,
            evidence,
            relation in {"same", "compatible"},
        )
        if polarity:
            return polarity
        if relation == "same":
            return "supports", "same_location"
        if relation == "compatible":
            return "related", "location_parent_child_compatible"
        if relation == "district_conflict":
            return "contradicts", "location_district_conflict"
        if relation == "conflict":
            return "contradicts", "location_conflict"
        return "related", "location_not_comparable"

    @staticmethod
    def _compare_event_time(target: AtomicClaim, evidence: AtomicClaim) -> tuple[str, str]:
        target_components = {
            key: target.slots.get(key) for key in ("event_date", "event_time") if target.slots.get(key)
        }
        evidence_components = {
            key: evidence.slots.get(key)
            for key in ("event_date", "event_time")
            if evidence.slots.get(key)
        }
        common = set(target_components) & set(evidence_components)
        same_common = bool(common) and all(
            target_components[key] == evidence_components[key] for key in common
        )
        polarity = StanceClassifier._polarity_decision(target, evidence, same_common)
        if polarity:
            return polarity
        if any(target_components[key] != evidence_components[key] for key in common):
            return "contradicts", "event_time_conflict"
        if not common:
            return "related", "event_time_not_comparable"
        if set(target_components) != set(evidence_components):
            return "related", "event_time_partial_match"
        return "supports", "same_event_time"

    @staticmethod
    def _compare_cause(target: AtomicClaim, evidence: AtomicClaim) -> tuple[str, str]:
        target_cause = target.slots.get("cause")
        evidence_cause = evidence.slots.get("cause")
        same = bool(target_cause and evidence_cause) and (
            StanceClassifier._normalize_value(target_cause)
            == StanceClassifier._normalize_value(evidence_cause)
        )
        if target_cause is None and evidence_cause is None:
            return "supports", "both_report_cause_under_investigation"
        if (
            target_cause is None
            or evidence_cause is None
            or target.certainty == "unconfirmed"
            or evidence.certainty == "unconfirmed"
        ):
            return "related", "cause_still_under_investigation"
        polarity = StanceClassifier._polarity_decision(target, evidence, same)
        if polarity:
            return polarity
        if same:
            return "supports", "same_specific_cause"
        return "contradicts", "specific_cause_conflict"

    @staticmethod
    def _compare_status(
        target: AtomicClaim,
        evidence: AtomicClaim,
        prefix: str,
    ) -> tuple[str, str]:
        left = target.slots.get("status")
        right = evidence.slots.get("status")
        if not left or not right or "unknown" in {left, right}:
            return "related", f"{prefix}_unknown"
        if left != right:
            return "contradicts", f"{prefix}_conflict"
        polarity = StanceClassifier._polarity_decision(target, evidence, True)
        return polarity or ("supports", f"same_{prefix}")

    @staticmethod
    def _compare_quantity(target: AtomicClaim, evidence: AtomicClaim) -> tuple[str, str]:
        if (
            target.slots.get("measure_type") == "generic_quantity"
            or evidence.slots.get("measure_type") == "generic_quantity"
        ):
            return "related", "quantity_semantics_missing"
        if target.slots.get("measure_type") != evidence.slots.get("measure_type"):
            return "related", "quantity_measure_type_mismatch"
        if target.slots.get("unit") != evidence.slots.get("unit"):
            return "related", "quantity_unit_not_comparable"
        same = target.slots.get("value") == evidence.slots.get("value")
        polarity = StanceClassifier._polarity_decision(target, evidence, same)
        if polarity:
            return polarity
        if same:
            return "supports", "same_quantity_semantics_and_value"
        return "contradicts", "quantity_value_conflict"

    @staticmethod
    def _polarity_decision(
        target: AtomicClaim,
        evidence: AtomicClaim,
        same_proposition: bool,
    ) -> tuple[str, str] | None:
        if "unknown" in {target.polarity, evidence.polarity}:
            return "related", "polarity_or_certainty_unknown"
        if target.polarity == evidence.polarity:
            if target.polarity == "negative" and not same_proposition:
                return "related", "different_negative_propositions"
            return None
        if same_proposition:
            reason = (
                "claim_explicitly_refuted"
                if "claim_explicitly_refuted"
                in {target.modality_reason, evidence.modality_reason}
                else "polarity_conflict"
            )
            return "contradicts", reason
        return "related", "different_propositions_with_different_polarity"

    @staticmethod
    def _uncertainty_decision(
        target: AtomicClaim,
        evidence: AtomicClaim,
    ) -> tuple[str, str] | None:
        target_uncertain = target.certainty == "unconfirmed" or target.polarity == "unknown"
        evidence_uncertain = (
            evidence.certainty == "unconfirmed" or evidence.polarity == "unknown"
        )
        target_is_refutation = target.modality_reason == "claim_explicitly_refuted"
        evidence_is_refutation = evidence.modality_reason == "claim_explicitly_refuted"
        if target_uncertain and not target_is_refutation:
            return "related", target.modality_reason or "claim_modality_unconfirmed"
        if evidence_uncertain and not evidence_is_refutation:
            return "related", evidence.modality_reason or "claim_modality_unconfirmed"
        return None

    @staticmethod
    def _time_relation(
        target: AtomicClaim,
        evidence: AtomicClaim,
        target_publish_time: str | None,
        evidence_publish_time: str | None,
    ) -> str:
        target_reference = target.slots.get("reference_time")
        evidence_reference = evidence.slots.get("reference_time")
        if isinstance(target_reference, dict) or isinstance(evidence_reference, dict):
            order = StanceClassifier._reference_time_order(
                target,
                evidence,
                target_publish_time,
                evidence_publish_time,
            )
            if order is None:
                return "not_comparable"
            if order == 0:
                return "same_time"
            return "target_earlier" if order > 0 else "target_later"
        target_time = StanceClassifier._parse_time(target_publish_time)
        evidence_time = StanceClassifier._parse_time(evidence_publish_time)
        if target_time is None or evidence_time is None:
            return "not_comparable"
        if target_time == evidence_time:
            return "same_time"
        return "target_earlier" if target_time < evidence_time else "target_later"

    @staticmethod
    def _dynamic_temporal_decision(
        target: AtomicClaim,
        evidence: AtomicClaim,
        time_relation: str,
    ) -> tuple[str, str] | None:
        if target.claim_type not in {
            "casualty",
            "response_status",
            "conclusion_status",
        }:
            return None
        if time_relation == "target_earlier":
            if StanceClassifier._is_forward_progression(target, evidence):
                return "updates", StanceClassifier._evolution_reason(target.claim_type)
            return None
        if time_relation == "target_later":
            if StanceClassifier._is_forward_progression(evidence, target):
                return "updates", "target_is_later_information_update"
            if StanceClassifier._dynamic_facts_differ(target, evidence):
                return "related", "target_is_later_information_update"
        return None

    @staticmethod
    def _is_forward_progression(earlier: AtomicClaim, later: AtomicClaim) -> bool:
        if earlier.claim_type != later.claim_type:
            return False
        if earlier.claim_type == "casualty":
            earlier_zero = (
                earlier.slots.get("count") == 0
                and earlier.slots.get("casualty_type") == "generic_casualty"
            )
            later_positive = (
                isinstance(later.slots.get("count"), int)
                and later.slots.get("count") > 0
                and later.polarity == "affirmative"
            )
            if earlier_zero and later_positive:
                return True
            return (
                earlier.polarity == later.polarity == "affirmative"
                and earlier.slots.get("casualty_type") == later.slots.get("casualty_type")
                and earlier.slots.get("count") != later.slots.get("count")
            )
        if earlier.claim_type == "response_status":
            order = {
                "not_started": 0,
                "started": 1,
                "ongoing": 2,
                "completed": 3,
            }
            left = earlier.slots.get("status")
            right = later.slots.get("status")
            return left in order and right in order and order[right] > order[left]
        order = {"under_investigation": 0, "preliminary": 1, "final": 2}
        left = earlier.slots.get("status")
        right = later.slots.get("status")
        return left in order and right in order and order[right] > order[left]

    @staticmethod
    def _evolution_reason(claim_type: str) -> str:
        return {
            "casualty": "casualty_information_evolved",
            "response_status": "response_status_evolved",
            "conclusion_status": "conclusion_status_evolved",
        }[claim_type]

    @staticmethod
    def _dynamic_facts_differ(target: AtomicClaim, evidence: AtomicClaim) -> bool:
        if target.claim_type == "casualty":
            return (
                target.slots.get("count"),
                target.slots.get("casualty_type"),
            ) != (
                evidence.slots.get("count"),
                evidence.slots.get("casualty_type"),
            )
        return target.slots.get("status") != evidence.slots.get("status")

    @staticmethod
    def _same_reference_time(target: AtomicClaim, evidence: AtomicClaim) -> bool:
        left = target.slots.get("reference_time")
        right = evidence.slots.get("reference_time")
        return bool(left and right and left == right)

    @staticmethod
    def _reference_time_order(
        target: AtomicClaim,
        evidence: AtomicClaim,
        target_publish_time: str | None,
        evidence_publish_time: str | None,
    ) -> int | None:
        left = target.slots.get("reference_time")
        right = evidence.slots.get("reference_time")
        left_resolved = EventEvolutionAnalyzer.resolve_reference_time(
            left,
            target_publish_time,
        )
        right_resolved = EventEvolutionAnalyzer.resolve_reference_time(
            right,
            evidence_publish_time,
        )
        if left_resolved is None or right_resolved is None:
            return None
        if left_resolved.sort_key[0] != right_resolved.sort_key[0]:
            return None
        if right_resolved.sort_key == left_resolved.sort_key:
            return 0
        return 1 if right_resolved.sort_key > left_resolved.sort_key else -1

    @staticmethod
    def _reference_time_key(value: dict) -> tuple[str, tuple[int, ...]] | None:
        datetime_value = value.get("event_datetime")
        if datetime_value:
            parsed = StanceClassifier._parse_time(datetime_value)
            if parsed:
                return (
                    "full_date_time",
                    (parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute),
                )
        date_value = value.get("event_date")
        time_value = value.get("event_time")
        if not time_value or not re.fullmatch(r"\d{2}:\d{2}", time_value):
            return None
        time_parts = tuple(int(part) for part in time_value.split(":"))
        if date_value and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
            date_parts = tuple(int(part) for part in date_value.split("-"))
            return "full_date_time", date_parts + time_parts
        if date_value and re.fullmatch(r"\d{2}-\d{2}", date_value):
            date_parts = tuple(int(part) for part in date_value.split("-"))
            return "month_day_time", date_parts + time_parts
        if not date_value:
            return "time_only", time_parts
        return None

    @staticmethod
    def _location_relation(left: dict, right: dict) -> str:
        left_province = left.get("province")
        right_province = right.get("province")
        if left_province and right_province and left_province != right_province:
            return "conflict"
        left_city = left.get("city") or left.get("province_or_city")
        right_city = right.get("city") or right.get("province_or_city")
        left_district = left.get("district")
        right_district = right.get("district")
        if left_city and right_city:
            if left_city != right_city:
                return "conflict"
            if left_district and right_district:
                return "same" if left_district == right_district else "district_conflict"
            return "same" if not left_district and not right_district else "compatible"
        if left_province and right_province:
            return "compatible" if left_province == right_province else "conflict"
        if (
            left.get("normalized_name") == right.get("normalized_name")
            and bool(left.get("normalized_name"))
        ):
            return "same"
        return "unknown"

    @staticmethod
    def _is_observational_zero_casualty(claim: AtomicClaim) -> bool:
        return (
            claim.claim_type == "casualty"
            and claim.slots.get("count") == 0
            and claim.slots.get("casualty_type") == "generic_casualty"
            and any(
                marker in claim.text
                for marker in (
                    "暂无人员伤亡",
                    "尚无人员伤亡",
                    "未发现人员伤亡",
                    "未发现伤亡",
                )
            )
        )

    @staticmethod
    def _zero_positive_casualty_pair(target: AtomicClaim, evidence: AtomicClaim) -> bool:
        if target.claim_type != "casualty" or evidence.claim_type != "casualty":
            return False
        counts = (target.slots.get("count"), evidence.slots.get("count"))
        return 0 in counts and any(
            isinstance(value, int) and value > 0 for value in counts
        )

    @staticmethod
    def _uncertain_pair(target: AtomicClaim, evidence: AtomicClaim) -> bool:
        return (
            target.certainty == "unconfirmed" or evidence.certainty == "unconfirmed"
        ) and target.certainty != evidence.certainty

    @staticmethod
    def _comparability(target: AtomicClaim, evidence: AtomicClaim) -> float:
        if target.claim_type != evidence.claim_type:
            return 0.0
        if target.claim_type == "casualty":
            return (
                3.0
                if target.slots.get("casualty_type")
                == evidence.slots.get("casualty_type")
                else 1.0
            )
        if target.claim_type == "quantity":
            same_measure = (
                target.slots.get("measure_type") == evidence.slots.get("measure_type")
            )
            same_unit = target.slots.get("unit") == evidence.slots.get("unit")
            return 3.0 if same_measure and same_unit else 2.0 if same_measure else 1.0 if same_unit else 0.5
        if target.claim_type == "location":
            return {
                "same": 3.0,
                "compatible": 2.0,
                "district_conflict": 1.5,
                "conflict": 1.0,
                "unknown": 0.5,
            }[StanceClassifier._location_relation(target.slots, evidence.slots)]
        if target.claim_type == "event_time":
            common = {
                key
                for key in ("event_date", "event_time")
                if target.slots.get(key) and evidence.slots.get(key)
            }
            return 1.0 + len(common)
        if target.claim_type == "response_status":
            return 3.0 if target.slots.get("action") == evidence.slots.get("action") else 1.0
        return 1.0

    @staticmethod
    def _relevance(target: AtomicClaim, evidence: AtomicClaim) -> float:
        lexical = StanceClassifier._text_similarity(target.text, evidence.text)
        if target.claim_type == evidence.claim_type:
            return min(0.75 + lexical * 0.25, 1.0)
        if target.claim_type == "other" or evidence.claim_type == "other":
            return lexical
        return lexical * 0.5

    def _as_claim(self, claim: AtomicClaim | str) -> AtomicClaim:
        if isinstance(claim, AtomicClaim):
            return claim
        extracted = self.extractor.extract_text(claim)
        if extracted:
            return extracted[0][1]
        return AtomicClaim(
            text=claim,
            target_quote=claim,
            claim_type="other",
            certainty="asserted",
            polarity="unknown",
            modality_reason=None,
            slots={},
            verifiable=True,
        )

    @staticmethod
    def _parse_time(value: str | None) -> datetime | None:
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
    def _normalize_value(value) -> str:
        return re.sub(r"\s+", "", str(value)).lower()

    @staticmethod
    def _text_similarity(left: str, right: str) -> float:
        left_terms = StanceClassifier._bigrams(left)
        right_terms = StanceClassifier._bigrams(right)
        if not left_terms or not right_terms:
            return 0.0
        return len(left_terms & right_terms) / len(left_terms | right_terms)

    @staticmethod
    def _bigrams(text: str) -> set[str]:
        normalized = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", text).lower()
        if len(normalized) < 2:
            return {normalized} if normalized else set()
        return {normalized[index : index + 2] for index in range(len(normalized) - 1)}
