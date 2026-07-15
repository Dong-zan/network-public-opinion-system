import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FactStructure:
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    claim_type: str | None = None
    time: str | None = None
    location: str | None = None
    polarity: str | None = None
    certainty: str | None = None
    modality: str | None = None


@dataclass(frozen=True)
class AtomizedClaim:
    atomic_claim_id: int
    parent_claim_id: int
    parent_claim: str
    text: str
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    claim_type: str | None = None
    time: str | None = None
    location: str | None = None
    polarity: str | None = None
    certainty: str | None = None
    inherited_context: dict[str, str] = field(default_factory=dict)


class ClaimAtomizer:
    """Split a parent claim into predicate-level claims without changing verification."""

    _predicate = re.compile(
        r"发布|举办|举行|迎来|分享|宣布|确认|证实|表示|回应|否认|"
        r"发生|造成|导致|引发|开展|启动|完成|进行|参加|抵达|离开|"
        r"救援|搜救|调查|通报|发现|拍摄|上传|转发|庆祝"
    )
    _coordinator = re.compile(r"并且|同时|并")
    _leading_coordinator = re.compile(r"^(?:并且|同时|并)\s*")
    _local_negation = re.compile(r"(?:并未|并不|没有|未|不)$")
    _subjectless_prefixes = (
        "在",
        "于",
        "通过",
        "当天",
        "当日",
        "今日",
        "昨日",
        "随后",
        "之后",
        "也",
        "仍",
        "已",
        "正在",
        "未",
        "没有",
        "不",
    )
    _fact_predicates = (
        (re.compile(r"迎来生日"), "birthday", "personal_event"),
        (re.compile(r"发布|分享|上传|晒出|发文|更新"), "publish", "social_post"),
        (re.compile(r"举办|举行|开展|庆祝"), "hold_activity", "activity"),
        (re.compile(r"造成"), "cause_result", "consequence"),
        (re.compile(r"发生"), "occur", "event"),
        (re.compile(r"确认|证实"), "confirm", "confirmation"),
        (re.compile(r"否认"), "deny", "denial"),
        (re.compile(r"宣布|表示|回应|通报"), "announce", "statement"),
        (re.compile(r"参加|参与"), "participate", "activity"),
        (re.compile(r"抵达|到达"), "arrive", "movement"),
        (re.compile(r"离开|离场"), "leave", "movement"),
    )
    _time_context = re.compile(
        r"(?:\d{4}年)?\d{1,2}月\d{1,2}日|"
        r"\d{4}-\d{1,2}-\d{1,2}|生日当天|近日|近期|"
        r"今日|昨日|当天|当日"
    )
    _location_context = re.compile(
        r"(?:在|于)(北京|上海|天津|重庆|"
        r"[一-鿿]{2,16}?(?:省|市|区|县|镇|村|路|街|现场))"
    )
    _modality_context = re.compile(
        r"据称|据传|网传|疑似|可能|或许|尚待核实|未经证实"
    )
    _negative_context = re.compile(r"没有|并未|并不|未曾|不曾|未|否认")
    _channel_context = re.compile(
        r"(?:在|通过)(?:社交平台|微博|网络|线上平台)"
    )

    def atomize(
        self,
        parent_claim: str,
        parent_claim_id: int = 1,
        atomic_id_start: int = 1,
    ) -> list[AtomizedClaim]:
        parent = parent_claim.strip().rstrip("。！？；;")
        if not parent:
            return []

        comma_clauses = [
            clause.strip()
            for clause in re.split(r"[，,]", parent)
            if clause.strip()
        ]
        leading_context: list[str] = []
        factual_clauses: list[str] = []
        for clause in comma_clauses:
            normalized = self._leading_coordinator.sub("", clause).strip()
            pieces = self._split_coordinated(normalized)
            for piece in pieces:
                if self._has_predicate(piece):
                    factual_clauses.append(piece)
                elif not factual_clauses:
                    leading_context.append(piece)
                else:
                    factual_clauses[-1] = f"{factual_clauses[-1]}，{piece}"

        if not factual_clauses:
            factual_clauses = [parent]

        shared_anchor = self._shared_anchor(factual_clauses[0])
        context = "，".join(leading_context)
        atoms: list[tuple[str, str]] = []
        for index, clause in enumerate(factual_clauses):
            text = clause
            if index > 0 and shared_anchor and not self._has_explicit_subject(clause):
                text = f"{shared_anchor}{clause}"
            if context:
                text = f"{context}，{text}"
            normalized = re.sub(r"\s+", " ", text).strip(" ，,")
            if normalized and all(normalized != item[0] for item in atoms):
                atoms.append((normalized, clause))

        result = []
        for index, (text, local_clause) in enumerate(atoms):
            structure = self._fact_structure(text)
            local_structure = self._fact_structure(local_clause)
            result.append(
                AtomizedClaim(
                    atomic_claim_id=atomic_id_start + index,
                    parent_claim_id=parent_claim_id,
                    parent_claim=parent,
                    text=text,
                    subject=structure.subject,
                    predicate=structure.predicate,
                    object=structure.object,
                    claim_type=structure.claim_type,
                    time=structure.time,
                    location=structure.location,
                    polarity=structure.polarity,
                    certainty=structure.certainty,
                    inherited_context=self._inherited_context(
                        structure,
                        local_structure,
                    ),
                )
            )
        return result

    def atomize_many(self, parent_claims: list[str]) -> list[AtomizedClaim]:
        result: list[AtomizedClaim] = []
        next_atomic_id = 1
        for parent_claim_id, parent_claim in enumerate(parent_claims, start=1):
            atoms = self.atomize(
                parent_claim,
                parent_claim_id=parent_claim_id,
                atomic_id_start=next_atomic_id,
            )
            result.extend(atoms)
            next_atomic_id += len(atoms)
        return result

    def _split_coordinated(self, text: str) -> list[str]:
        for match in self._coordinator.finditer(text):
            left = text[: match.start()].strip()
            right = text[match.end() :].strip()
            if self._has_predicate(left) and self._has_predicate(right):
                return [
                    *self._split_coordinated(left),
                    *self._split_coordinated(right),
                ]
        return [text]

    def _shared_anchor(self, text: str) -> str:
        predicate = self._predicate.search(text)
        if not predicate:
            return ""
        anchor = text[: predicate.start()].strip()
        # Predicate-local negation must not leak into a later positive clause.
        return self._local_negation.sub("", anchor).strip()

    def _has_explicit_subject(self, text: str) -> bool:
        predicate = self._predicate.search(text)
        if not predicate or predicate.start() == 0:
            return False
        prefix = text[: predicate.start()].strip()
        return bool(prefix) and not prefix.startswith(self._subjectless_prefixes)

    def _has_predicate(self, text: str) -> bool:
        return bool(self._predicate.search(text))

    def _fact_structure(self, text: str) -> FactStructure:
        predicate_match = self._fact_predicate_match(text)
        if predicate_match is None:
            return FactStructure()
        match, predicate, claim_type = predicate_match
        prefix = text[: match.start()]
        object_text = text[match.end() :].strip(" ，,。；;") or None
        time_match = self._time_context.search(text)
        location_match = self._location_context.search(text)
        modality_match = self._modality_context.search(text)
        subject = self._subject(prefix)
        if predicate == "birthday":
            object_text = None
        elif predicate == "cause_result" and object_text and re.search(
            r"\d+\s*(?:人|名).*(?:死亡|遇难|受伤|失踪)",
            object_text,
        ):
            claim_type = "casualty"
        certainty = (
            "unconfirmed"
            if modality_match
            else "confirmed"
            if predicate == "confirm"
            else "asserted"
        )
        return FactStructure(
            subject=subject,
            predicate=predicate,
            object=object_text,
            claim_type=claim_type,
            time=time_match.group(0) if time_match else None,
            location=location_match.group(1) if location_match else None,
            polarity=(
                "negative"
                if self._negative_context.search(prefix)
                else "unknown"
                if modality_match
                else "affirmative"
            ),
            certainty=certainty,
            modality=modality_match.group(0) if modality_match else None,
        )

    def _fact_predicate_match(
        self,
        text: str,
    ) -> tuple[re.Match[str], str, str] | None:
        matches = []
        for pattern, predicate, claim_type in self._fact_predicates:
            match = pattern.search(text)
            if match:
                matches.append((match.start(), -len(match.group(0)), match, predicate, claim_type))
        if not matches:
            return None
        _, _, match, predicate, claim_type = min(matches, key=lambda item: item[:2])
        return match, predicate, claim_type

    def _subject(self, prefix: str) -> str | None:
        value = self._modality_context.sub("", prefix)
        value = self._time_context.sub("", value)
        value = self._location_context.sub("", value)
        value = self._channel_context.sub("", value)
        value = self._negative_context.sub("", value)
        value = re.sub(r"^(?:随后|之后|也|仍|已|正在)", "", value)
        normalized = re.sub(r"[^一-鿿A-Za-z0-9]", "", value)
        return normalized or None

    @staticmethod
    def _inherited_context(
        structure: FactStructure,
        local: FactStructure,
    ) -> dict[str, str]:
        inherited = {}
        for name in ("subject", "time", "location"):
            value = getattr(structure, name)
            if value is not None and getattr(local, name) is None:
                inherited[name] = value
        if structure.certainty and structure.certainty != local.certainty:
            inherited["certainty"] = structure.certainty
        if structure.polarity and structure.polarity != local.polarity:
            inherited["polarity"] = structure.polarity
        if structure.modality and structure.modality != local.modality:
            inherited["modality"] = structure.modality
        return inherited
