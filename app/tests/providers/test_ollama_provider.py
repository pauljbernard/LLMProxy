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


def test_ollama_provider_batches_embeddings_in_one_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embed"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "qwen2.5-coder:14b"
        assert payload["input"] == ["hello world", "goodbye world"]
        return httpx.Response(
            200,
            json={
                "embeddings": [
                    [0.1, 0.2, 0.3],
                    [0.4, 0.5, 0.6],
                ]
            },
        )

    provider = OllamaProvider(
        "qwen2.5-coder:14b",
        base_url="http://localhost:11434",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.embed(["hello world", "goodbye world"]))

    assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]


def test_ollama_provider_streams_chat_chunks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["stream"] is True
        return httpx.Response(
            200,
            text=(
                '{"model":"qwen2.5-coder:14b","message":{"role":"assistant","content":"Ollama "},"done":false}\n'
                '{"model":"qwen2.5-coder:14b","message":{"role":"assistant","content":"answer."},"done":true,"done_reason":"stop","prompt_eval_count":14,"eval_count":2}\n'
            ),
        )

    provider = OllamaProvider(
        "qwen2.5-coder:14b",
        base_url="http://localhost:11434",
        transport=httpx.MockTransport(handler),
    )

    chunks = asyncio.run(_collect(provider.stream_chat(_request())))

    assert [chunk["delta"] for chunk in chunks] == ["Ollama ", "answer."]
    assert chunks[-1]["finish_reason"] == "stop"
    assert chunks[-1]["input_tokens"] == 14
    assert chunks[-1]["output_tokens"] == 2


async def _collect(stream) -> list[dict[str, object]]:
    return [chunk async for chunk in stream]
