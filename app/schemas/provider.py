"""Provider schemas."""

from pydantic import BaseModel, Field


class ProviderRequestShape(BaseModel):
    accepts_temperature: bool = True
    accepts_top_p: bool = True
    accepts_stop_sequences: bool = True


class ProviderCapability(BaseModel):
    provider_family: str
    provider_name: str
    model_id: str
    supports_streaming: bool = True
    supports_embeddings: bool = False
    supports_tools: bool = False
    max_context_tokens: int = 0
    max_output_tokens: int = 0
    request_shape: ProviderRequestShape = Field(default_factory=ProviderRequestShape)
