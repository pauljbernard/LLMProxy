"""Judge logic for teacher ensembles."""

from app.schemas.ensemble import JudgeCritiquePayload, TeacherCandidate


def judge_response(
    candidates: list[TeacherCandidate],
    *,
    domain: str,
) -> JudgeCritiquePayload:
    scored = sorted(candidates, key=lambda item: (item.score, len(item.content)), reverse=True)
    winner = scored[0]
    domain_bonus = 0.03 if domain == "software_architecture" and winner.provider == "anthropic" else 0.0
    rationale = f"Selected {winner.provider} based on ensemble score, response depth, and domain fit."
    return JudgeCritiquePayload(
        judge_provider="rule_based_judge",
        judge_model="heuristic-v1",
        selected_response_id=winner.response_id,
        selected_provider=winner.provider,
        selected_model=winner.model,
        rationale=rationale,
        scores={
            candidate.response_id: round(candidate.score + (domain_bonus if candidate.response_id == winner.response_id else 0.0), 4)
            for candidate in scored
        },
    )
