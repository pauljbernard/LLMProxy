from app.proxy.judge import judge_response
from app.schemas.ensemble import TeacherCandidate


def test_judge_selects_highest_scored_candidate() -> None:
    candidates = [
        TeacherCandidate(
            response_id="resp_openai",
            provider="openai",
            provider_family="OpenAI",
            model="gpt-4.1-mini",
            content="Short answer.",
            score=0.90,
            rationale="candidate 1",
        ),
        TeacherCandidate(
            response_id="resp_anthropic",
            provider="anthropic",
            provider_family="Anthropic",
            model="claude-3-5-sonnet",
            content="Longer architecture answer.",
            score=0.95,
            rationale="candidate 2",
        ),
    ]

    critique = judge_response(candidates, domain="software_architecture")

    assert critique.selected_response_id == "resp_anthropic"
    assert critique.selected_provider == "anthropic"
    assert "resp_anthropic" in critique.scores
