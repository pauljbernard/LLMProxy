import asyncio
import json

import httpx

from app.providers.ollama import OllamaProvider
from app.schemas.chat import ChatCompletionRequest


def _request() -> ChatCompletionRequest:
    return ChatCompletionRequest.model_validate(
        {
            "model": "proxy-local",
            "messages": [{"role": "user", "content": "Review this coding patch."}],
            "metadata": {"session_id": "sess_ollama"},
        }
    )


def test_ollama_provider_normalizes_chat_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "qwen2.5-coder:14b"
        assert payload["messages"][0]["content"] == "Review this coding patch."
        return httpx.Response(
            200,
            json={
                "model": "qwen2.5-coder:14b",
                "message": {"role": "assistant", "content": "Ollama coding answer."},
                "done_reason": "stop",
                "prompt_eval_count": 14,
                "eval_count": 5,
            },
        )

    provider = OllamaProvider(
        "qwen2.5-coder:14b",
        base_url="http://localhost:11434",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.invoke(_request()))

    assert result["model"] == "qwen2.5-coder:14b"
    assert result["content"] == "Ollama coding answer."
    assert result["provider"] == "ollama"
    assert result["provider_family"] == "local runtime"
    assert result["input_tokens"] == 14
    assert result["output_tokens"] == 5
    assert result["cost_estimate"] == 0.0
