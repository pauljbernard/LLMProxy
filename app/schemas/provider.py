"""Provider schemas."""

from pydantic import BaseModel


class ProviderCapability(BaseModel):
    provider_family: str
    provider_name: str
    model_id: str
    supports_streaming: bool = True
    supports_embeddings: bool = False
    supports_tools: bool = False
    max_context_tokens: int = 0
    max_output_tokens: int = 0
