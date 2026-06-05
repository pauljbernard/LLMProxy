# Provider Strategy

## Purpose

The proxy is not only a facade for local models and a training-data capture point. It is also a production routing layer across frontier and local model ecosystems.

The proxy must treat major frontier providers as first-class runtime backends while preserving a normalized interface for routing, evaluation, logging, and fallback.

## Required First-Class Provider Families

The system must support first-class adapters for:

- OpenAI
- Anthropic
- Google Gemini
- xAI
- AWS Bedrock
- Azure OpenAI

The system may additionally support other OpenAI-compatible or hosted providers, but the six families above are the required strategic baseline.

## Provider Capability Matrix

For each first-class provider family, the proxy should capture and expose:

- supported chat-completion models
- supported reasoning or premium models
- supported embeddings models where applicable
- streaming support
- tool-calling support if available
- context-window metadata
- pricing metadata
- rate-limit metadata if available
- region or deployment metadata where applicable
- auth and endpoint configuration requirements

## Normalized Provider Capabilities

The provider layer must normalize at least these runtime capabilities:

- `provider_family`
- `provider_name`
- `model_id`
- `model_class`
- `supports_streaming`
- `supports_embeddings`
- `supports_tools`
- `max_context_tokens`
- `max_output_tokens`
- `input_cost_per_1k`
- `output_cost_per_1k`
- `latency_profile`
- `availability_status`
- `privacy_class`
- `deployment_scope`

## Hosted Provider Coverage

The proxy must support these hosted access patterns:

- direct vendor APIs
- Azure-hosted OpenAI deployments
- AWS Bedrock-hosted model access

Hosted-provider support must be treated as a routing dimension, not an implementation detail. The proxy must be able to choose among direct and hosted backends based on policy.

## Fallback Policy

Every provider-backed route must define:

- primary provider and model
- secondary fallback provider and model
- tertiary fallback when required for critical paths
- retry policy
- timeout policy
- circuit-breaker or health-degradation policy

Fallback decisions must preserve audit data showing:

- original target
- failure reason
- fallback target
- latency impact
- cost impact

## Provider Health and Reliability

The proxy must collect and retain provider-health signals including:

- success rate
- error rate
- timeout rate
- average latency
- p95 latency
- rate-limit failures
- provider unavailability incidents
- schema or compatibility failures

Provider-health data must influence routing eligibility for future requests.

## Provider Selection Constraints

Provider selection must consider:

- task domain fit
- benchmark performance
- session privacy mode
- user or operator budget policy
- context-window requirements
- tool-use requirements
- latency tolerance
- availability and health
- region or hosting constraints

## Best-of-Breed Standard

The proxy is best-of-breed only if it can:

1. route across the full required provider set
2. normalize their capabilities and outputs
3. choose among them using explicit policy
4. fail over safely when a provider degrades
5. compare frontier and local options on quality, cost, and latency
6. preserve enough telemetry to improve routing over time
