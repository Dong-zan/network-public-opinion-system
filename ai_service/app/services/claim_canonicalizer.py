import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from app.services.claim_extractor import AtomicClaim


@dataclass(frozen=True)
class CanonicalClaim:
    cluster_id: str
    claim_type: str
    canonical_slots: dict[str, Any]
    polarity: str
    certainty: str


class ClaimCanonicalizer:
    def canonicalize(self, claim: AtomicClaim) -> CanonicalClaim:
        slots = {
            key: self._normalize_value(value)
            for key, value in claim.slots.items()
            if key != "reference_time"
        }
        if claim.claim_type == "quantity" and slots.get("measure_type") not in {
            None,
            "generic_quantity",
        }:
            slots = {
                key: slots[key]
                for key in ("value", "unit", "measure_type")
                if key in slots
            }
        if claim.claim_type == "other" and not slots:
            slots = {"text": self._normalize_text(claim.text)}
        payload = {
            "claim_type": claim.claim_type,
            "slots": slots,
            "polarity": claim.polarity,
        }
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        return CanonicalClaim(
            cluster_id=f"claim-cluster:{digest}",
            claim_type=claim.claim_type,
            canonical_slots=slots,
            polarity=claim.polarity,
            certainty=claim.certainty,
        )

    @classmethod
    def _normalize_value(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: cls._normalize_value(value[key])
                for key in sorted(value)
            }
        if isinstance(value, list):
            return [cls._normalize_value(item) for item in value]
        if isinstance(value, str):
            return cls._normalize_text(value)
        return value

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", "", value).strip().lower()
