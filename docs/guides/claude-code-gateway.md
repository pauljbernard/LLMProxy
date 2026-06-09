# Claude Code Gateway

Use this guide when you want `Claude Code` to call `llmProxy` instead of connecting directly to Anthropic.

This flow requires two things:

1. `llmProxy` must expose the Anthropic-compatible inbound gateway endpoints:
   - `POST /v1/messages`
   - `POST /v1/messages/count_tokens`
2. `llmProxy` must have a healthy outbound route to a model that can satisfy the request.

## What `llmProxy` now supports

`llmProxy` now accepts Anthropic-style gateway traffic on the same front door used for the rest of the proxy:

```text
http://127.0.0.1:8000
```

The gateway surface is authenticated with the same operator or virtual-key token model already used by the proxy.

Supported inbound auth forms:

- `Authorization: Bearer <token>`
- `Authorization: <token>`
- `X-API-Key: <token>`

## Required `llmProxy` runtime configuration

At minimum, make sure the target outbound provider is actually healthy.

For Anthropic direct API routing, that usually means:

```bash
export LLMPROXY_ANTHROPIC_API_KEY=your-anthropic-key
export LLMPROXY_ANTHROPIC_MODEL=claude-3-5-sonnet
```

If you intend to route Claude Code traffic somewhere else through policy or fallback, make sure that destination is healthy and reachable instead.

Verify with:

```bash
curl http://127.0.0.1:8000/health
```

Look for the `anthropic` provider readiness state if you expect direct Anthropic routing.

## Claude Code environment variables

Point Claude Code at `llmProxy` with:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8000
export ANTHROPIC_AUTH_TOKEN=change-me
export ANTHROPIC_MODEL=claude-3-5-sonnet
```

If you want Claude Code to discover models dynamically from the gateway, also enable:

```bash
export CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1
```

Use a real operator token or virtual key instead of `change-me` outside local development.

## Smoke tests

### Count tokens

```bash
curl http://127.0.0.1:8000/v1/messages/count_tokens \
  -H 'Authorization: Bearer change-me' \
  -H 'content-type: application/json' \
  -H 'anthropic-version: 2023-06-01' \
  -d '{
    "model": "claude-3-5-sonnet",
    "max_tokens": 64,
    "messages": [
      {"role": "user", "content": "hello from Claude Code"}
    ]
  }'
```

### Non-streaming message

```bash
curl http://127.0.0.1:8000/v1/messages \
  -H 'Authorization: Bearer change-me' \
  -H 'content-type: application/json' \
  -H 'anthropic-version: 2023-06-01' \
  -d '{
    "model": "claude-3-5-sonnet",
    "max_tokens": 128,
    "messages": [
      {"role": "user", "content": "Say hello in one sentence."}
    ]
  }'
```

### Streaming message

```bash
curl http://127.0.0.1:8000/v1/messages \
  -H 'Authorization: Bearer change-me' \
  -H 'content-type: application/json' \
  -H 'anthropic-version: 2023-06-01' \
  -d '{
    "model": "claude-3-5-sonnet",
    "stream": true,
    "max_tokens": 128,
    "messages": [
      {"role": "user", "content": "Stream a short hello."}
    ]
  }'
```

Expected event types include:

- `message_start`
- `content_block_start`
- `content_block_delta`
- `message_delta`
- `message_stop`

## Important routing note

Claude Code only knows it is talking to an Anthropic-compatible gateway. It does not know or care whether `llmProxy` ultimately routes that request to:

- direct Anthropic
- Bedrock Anthropic
- a local fallback
- another routed target

So a successful Claude Code request proves the gateway surface works, but it does not by itself prove the request landed on Anthropic. Use `Observability > Traffic` and request detail to confirm the actual selected provider and model.

## Troubleshooting

If Claude Code still fails:

1. Check `GET /health` and confirm the intended outbound provider is healthy.
2. Verify the token works against `POST /v1/messages/count_tokens`.
3. Verify the listener you are targeting exposes the proxy surface.
4. If the request succeeds but lands on the wrong provider, inspect `Models > Routing`.
5. If Anthropic is unavailable, expect policy fallback behavior unless you explicitly constrain the route.

## References

- [API Usage Reference](../reference/api-usage.md)
- [Configuration Reference](../reference/configuration.md)
- [Operator Console Guide](./operator-console.md)
- [Anthropic Claude Code LLM gateway docs](https://docs.anthropic.com/en/docs/claude-code/llm-gateway)
