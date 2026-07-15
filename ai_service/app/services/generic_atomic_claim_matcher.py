import re
from dataclasses import dataclass

from app.services.claim_extractor import AtomicClaim


@dataclass(frozen=True)
class GenericAtomicMatch:
    stance: str
    reason_code: str


@dataclass(frozen=True)
class GenericAtomicFrame:
    subject: str
    predicate: str
    object_text: str
    negated: bool
    uncertain: bool
    time: str | None
    location: str | None


class GenericAtomicClaimMatcher:
    """Deterministic semantic-frame matcher for unstructured atomic facts."""

    _predicate_groups = {
        "social_publish": ("发布", "分享", "上传", "晒出", "发文", "更新"),
        "hold_event": ("举办", "举行", "开展", "庆祝"),
        "announce": ("宣布", "表示", "回应", "通报"),
        "arrive": ("抵达", "到达"),
        "leave": ("离开", "离场"),
        "participate": ("参加", "参与"),
    }
    _structured_predicate_aliases = {
        "publish": "social_publish",
        "social_publish": "social_publish",
        "hold_activity": "hold_event",
        "hold_event": "hold_event",
        "announce": "announce",
        "arrive": "arrive",
        "leave": "leave",
        "participate": "participate",
    }
    _uncertain = re.compile(r"据称|据传|网传|疑似|可能|或许|尚待核实|未经证实")
    _negated = re.compile(r"(?:没有|并未|未曾|不曾|未|否认)\s*[^，。；;]{0,8}$")
    _time = re.compile(
        r"(?:\d{4}年)?\d{1,2}月\d{1,2}日|"
        r"\d{4}-\d{1,2}-\d{1,2}|近日|近期|今日|昨日|当天|当日"
    )
    _location = re.compile(
        r"(?:在|于)([一-鿿]{2,16}?(?:省|市|区|县|镇|村|路|街|现场))"
    )
    _non_subject_context = re.compile(
        r"据称|据传|网传|疑似|可能|或许|尚待核实|未经证实|"
        r"(?:\d{4}年)?\d{1,2}月\d{1,2}日|\d{4}-\d{1,2}-\d{1,2}|"
        r"生日当天|近日|近期|今日|昨日|当天|当日|"
        r"(?:在|通过)(?:社交平台|微博|网络|线上平台)|"
        r"没有|并未|未曾|不曾|未|否认"
    )

    def match(
        self,
        target: AtomicClaim,
        evidence: AtomicClaim,
    ) -> GenericAtomicMatch:
        target_frame = self._frame(target)
        evidence_frame = self._frame(evidence)
        if target_frame is None or evidence_frame is None:
            return GenericAtomicMatch("related", "generic_frame_incomplete")
        if target_frame.subject != evidence_frame.subject:
            return GenericAtomicMatch("related", "generic_subject_mismatch")
        if target_frame.predicate != evidence_frame.predicate:
            return GenericAtomicMatch("related", "generic_predicate_mismatch")
        if not self._objects_compatible(target_frame, evidence_frame):
            return GenericAtomicMatch("related", "generic_object_not_comparable")
        if self._times_conflict(target_frame.time, evidence_frame.time):
            return GenericAtomicMatch("contradicts", "generic_time_conflict")
        if target_frame.location and evidence_frame.location and (
            target_frame.location != evidence_frame.location
        ):
            return GenericAtomicMatch("contradicts", "generic_location_conflict")
        if target_frame.uncertain != evidence_frame.uncertain:
            return GenericAtomicMatch("related", "generic_modality_mismatch")
        if target_frame.uncertain:
            return GenericAtomicMatch("related", "generic_modality_unconfirmed")
        if target_frame.negated != evidence_frame.negated:
            return GenericAtomicMatch("contradicts", "generic_polarity_conflict")
        return GenericAtomicMatch("supports", "generic_semantic_support")

    def _frame(self, claim: AtomicClaim) -> GenericAtomicFrame | None:
        if self._has_structured_frame(claim):
            return self._structured_frame(claim)
        return self._text_frame(claim.text)

    @staticmethod
    def _has_structured_frame(claim: AtomicClaim) -> bool:
        return any(
            value is not None
            for value in (
                claim.subject,
                claim.predicate,
                claim.object,
                claim.time,
                claim.location,
            )
        )

    def _structured_frame(self, claim: AtomicClaim) -> GenericAtomicFrame | None:
        subject = self._normalize_text(claim.subject or "")
        predicate = self._structured_predicate_aliases.get(claim.predicate or "")
        if not subject or predicate is None:
            return None
        return GenericAtomicFrame(
            subject=subject,
            predicate=predicate,
            object_text=self._normalize_text(claim.object or ""),
            negated=claim.polarity == "negative",
            uncertain=(
                claim.certainty == "unconfirmed" or claim.polarity == "unknown"
            ),
            time=claim.time,
            location=claim.location,
        )

    def _text_frame(self, text: str) -> GenericAtomicFrame | None:
        predicate_match = self._predicate_match(text)
        if predicate_match is None:
            return None
        predicate, start, end = predicate_match
        prefix = text[:start]
        subject = self._normalize_subject(prefix)
        if not subject:
            return None
        location_match = self._location.search(text)
        time_match = self._time.search(text)
        return GenericAtomicFrame(
            subject=subject,
            predicate=predicate,
            object_text=self._normalize_text(text[end:]),
            negated=bool(self._negated.search(prefix)),
            uncertain=bool(self._uncertain.search(text)),
            time=time_match.group(0) if time_match else None,
            location=location_match.group(1) if location_match else None,
        )

    def _predicate_match(self, text: str) -> tuple[str, int, int] | None:
        matches = []
        for canonical, values in self._predicate_groups.items():
            for value in values:
                match = re.search(re.escape(value), text)
                if match:
                    matches.append((match.start(), -len(value), canonical, match.end()))
        if not matches:
            return None
        start, _, canonical, end = min(matches)
        return canonical, start, end

    @staticmethod
    def _times_conflict(left: str | None, right: str | None) -> bool:
        if not left or not right or left == right:
            return False
        vague = {"近日", "近期", "当天", "当日"}
        if left in vague or right in vague:
            return False
        return True

    def _normalize_subject(self, prefix: str) -> str:
        value = self._non_subject_context.sub("", prefix)
        value = re.sub(r"(?:在|于|通过)[^，。；;]{1,16}$", "", value)
        return self._normalize_text(value)

    def _objects_compatible(
        self,
        target: GenericAtomicFrame,
        evidence: GenericAtomicFrame,
    ) -> bool:
        left = self._object_features(target.predicate, target.object_text)
        right = self._object_features(evidence.predicate, evidence.object_text)
        if target.predicate == "social_publish":
            return {"birthday", "media_content"} <= left and {
                "birthday",
                "media_content",
            } <= right
        if target.predicate == "hold_event":
            return bool({"birthday", "event"} <= left and {"birthday", "event"} <= right)
        return bool(
            target.object_text
            and evidence.object_text
            and (
                target.object_text == evidence.object_text
                or target.object_text in evidence.object_text
                or evidence.object_text in target.object_text
            )
        )

    @staticmethod
    def _object_features(predicate: str, value: str) -> set[str]:
        features = set()
        if any(marker in value for marker in ("生日", "庆生")):
            features.add("birthday")
        if any(marker in value for marker in ("动态", "照片", "图片", "视频", "内容")):
            features.add("media_content")
        if any(marker in value for marker in ("活动", "生日会", "庆祝会", "派对")):
            features.add("event")
        if predicate not in {"social_publish", "hold_event"} and value:
            features.add("generic_object")
        return features

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"[^一-鿿A-Za-z0-9]", "", value).lower()
