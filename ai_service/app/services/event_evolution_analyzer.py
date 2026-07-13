from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.services.claim_extractor import AtomicClaim


@dataclass(frozen=True)
class ClaimTime:
    display: str
    source: str
    sort_key: tuple[int, ...]
    precision: str
    year_inferred: bool
    normalized_time: str | None = None


class EventEvolutionAnalyzer:
    @classmethod
    def resolve_reference_time(
        cls,
        reference: dict[str, Any] | None,
        publish_time: str | None,
    ) -> ClaimTime | None:
        if not isinstance(reference, dict):
            return None
        return cls._from_components(
            reference,
            "reference_time",
            cls._parse_datetime(publish_time),
        )

    def resolve_time(
        self,
        claim: AtomicClaim,
        publish_time: str | None,
    ) -> ClaimTime | None:
        reference = claim.slots.get("reference_time")
        publish_datetime = self._parse_datetime(publish_time)
        if isinstance(reference, dict):
            resolved = self.resolve_reference_time(reference, publish_time)
            if resolved:
                return resolved
        if claim.claim_type == "event_time":
            resolved = self._from_components(
                claim.slots,
                "event_time",
                publish_datetime,
            )
            if resolved:
                return resolved
        parsed = self._parse_datetime(publish_time)
        if parsed:
            return ClaimTime(
                display=parsed.isoformat(timespec="minutes"),
                source="publish_time",
                sort_key=(0, parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute),
                precision="publish_datetime",
                year_inferred=False,
                normalized_time=parsed.isoformat(timespec="minutes"),
            )
        return None

    @staticmethod
    def _from_components(
        values: dict[str, Any],
        source: str,
        publish_datetime: datetime | None,
    ) -> ClaimTime | None:
        date_value = str(values.get("event_date") or "")
        time_value = str(values.get("event_time") or "")
        if date_value and time_value:
            if len(date_value) == 10:
                parts = tuple(int(item) for item in date_value.split("-"))
                time_parts = tuple(int(item) for item in time_value.split(":"))
                return ClaimTime(
                    display=f"{date_value}T{time_value}",
                    source=source,
                    sort_key=(0, *parts, *time_parts),
                    precision="full_datetime",
                    year_inferred=False,
                    normalized_time=f"{date_value}T{time_value}",
                )
            parts = tuple(int(item) for item in date_value.split("-"))
            time_parts = tuple(int(item) for item in time_value.split(":"))
            inferred = EventEvolutionAnalyzer._infer_month_day_datetime(
                parts,
                time_parts,
                publish_datetime,
            )
            if inferred:
                return ClaimTime(
                    display=f"{date_value}T{time_value}",
                    source=source,
                    sort_key=(
                        0,
                        inferred.year,
                        inferred.month,
                        inferred.day,
                        inferred.hour,
                        inferred.minute,
                    ),
                    precision="month_day_time",
                    year_inferred=True,
                    normalized_time=inferred.isoformat(timespec="minutes"),
                )
            return ClaimTime(
                display=f"{date_value}T{time_value}",
                source=source,
                sort_key=(1, *parts, *time_parts),
                precision="month_day_time",
                year_inferred=False,
                normalized_time=None,
            )
        if date_value:
            parts = tuple(int(item) for item in date_value.split("-"))
            inferred = (
                EventEvolutionAnalyzer._infer_month_day_datetime(
                    parts,
                    (0, 0),
                    publish_datetime,
                )
                if len(parts) == 2
                else None
            )
            if inferred:
                return ClaimTime(
                    display=date_value,
                    source=source,
                    sort_key=(0, inferred.year, inferred.month, inferred.day, 0, 0),
                    precision="month_day",
                    year_inferred=True,
                    normalized_time=inferred.date().isoformat(),
                )
            return ClaimTime(
                display=date_value,
                source=source,
                sort_key=(
                    (0 if len(parts) == 3 else 1),
                    *parts,
                    0,
                    0,
                ),
                precision=("full_date" if len(parts) == 3 else "month_day"),
                year_inferred=False,
                normalized_time=(date_value if len(parts) == 3 else None),
            )
        if time_value:
            parts = tuple(int(item) for item in time_value.split(":"))
            return ClaimTime(
                display=time_value,
                source=source,
                sort_key=(2, *parts),
                precision="time_only",
                year_inferred=False,
                normalized_time=None,
            )
        return None

    @staticmethod
    def _infer_month_day_datetime(
        date_parts: tuple[int, ...],
        time_parts: tuple[int, ...],
        publish_datetime: datetime | None,
        *,
        max_distance_days: int = 90,
    ) -> datetime | None:
        if publish_datetime is None or len(date_parts) != 2 or len(time_parts) != 2:
            return None
        month, day = date_parts
        hour, minute = time_parts
        candidates = []
        for year in range(publish_datetime.year - 1, publish_datetime.year + 2):
            try:
                candidates.append(datetime(year, month, day, hour, minute))
            except ValueError:
                continue
        if not candidates:
            return None
        nearest = min(candidates, key=lambda item: abs(item - publish_datetime))
        if abs(nearest - publish_datetime).total_seconds() > max_distance_days * 24 * 60 * 60:
            return None
        return nearest

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
