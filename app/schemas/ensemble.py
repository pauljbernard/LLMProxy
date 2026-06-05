"""Schemas for teacher ensemble execution."""

from pydantic import BaseModel

from app.schemas.chat import ChatCompletionResponse


class TeacherCandidate(BaseModel):
    response_id: str
    provider: str
    provider_family: str
    model: str
    content: str
    score: float
    rationale: str


class JudgeCritiquePayload(BaseModel):
    judge_provider: str
    judge_model: str
    selected_response_id: str
    selected_provider: str
    selected_model: str
    rationale: str
    scores: dict[str, float]


class EnsembleResponse(BaseModel):
    response: ChatCompletionResponse
    teacher_candidates: list[TeacherCandidate]
    judge_critique: JudgeCritiquePayload
