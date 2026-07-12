from app.schemas.verification import ClaimVerificationResult


class VerificationScorer:
    def score_claim(self, result: ClaimVerificationResult) -> float | None:
        if result.verdict == "not_verifiable":
            return None
        if not result.evidence:
            return 0.0
        source_count = result.independent_source_count
        if result.verdict in {"supported", "contradicted"}:
            return min(70.0 + source_count * 10.0, 95.0)
        if result.verdict == "conflicting":
            return min(60.0 + source_count * 5.0, 85.0)
        return min(20.0 + source_count * 10.0, 50.0)

    def score(
        self,
        results: list[ClaimVerificationResult],
        overall_verdict: str | None = None,
    ) -> float:
        selected = self._results_for_overall(results, overall_verdict)
        values = [
            value
            for result in selected
            if (value := self.score_claim(result)) is not None
        ]
        return round(sum(values) / len(values), 1) if values else 0.0

    @staticmethod
    def _results_for_overall(
        results: list[ClaimVerificationResult],
        overall_verdict: str | None,
    ) -> list[ClaimVerificationResult]:
        if overall_verdict in {"supported", "contradicted", "insufficient_evidence"}:
            return [result for result in results if result.verdict == overall_verdict]
        if overall_verdict == "conflicting":
            conflicting = [result for result in results if result.verdict == "conflicting"]
            if conflicting:
                return conflicting
            return [
                result
                for result in results
                if result.verdict in {"supported", "contradicted"}
            ]
        if overall_verdict == "not_verifiable":
            return []
        return [result for result in results if result.verdict != "not_verifiable"]
