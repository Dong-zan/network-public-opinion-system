from app.schemas.verification import ClaimVerificationResult


class VerificationScorer:
    def score_claim(self, result: ClaimVerificationResult) -> float | None:
        if result.verdict == "not_verifiable":
            return None
        if not result.evidence or result.independent_source_count <= 0:
            return 0.0
        source_count = result.independent_source_count
        if source_count == 1:
            return 30.0
        if result.verdict in {"supported", "contradicted"}:
            return min(70.0 + source_count * 10.0, 95.0)
        if result.verdict == "conflicting":
            return min(60.0 + source_count * 5.0, 85.0)
        return min(30.0 + (source_count - 1) * 10.0, 70.0)

    def score(
        self,
        results: list[ClaimVerificationResult],
        overall_verdict: str | None = None,
        weights: list[float] | None = None,
    ) -> float:
        del overall_verdict  # Verdict never filters evidence strength.
        if weights is None:
            weights = [1.0] * len(results)
        if len(weights) != len(results):
            raise ValueError("weights must align with verification results")

        weighted_total = 0.0
        total_weight = 0.0
        for result, weight in zip(results, weights):
            if weight <= 0:
                continue
            value = (
                result.evidence_score
                if result.evidence_score is not None
                else self.score_claim(result)
            )
            if value is None:
                continue
            weighted_total += value * weight
            total_weight += weight
        return round(weighted_total / total_weight, 1) if total_weight else 0.0
