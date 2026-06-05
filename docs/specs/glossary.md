# Glossary

## Purpose

This glossary defines the canonical terms used across the spec pack so that future implementation agents do not drift in meaning.

## Terms

### Frontier Model

A high-capability model served by a major external provider or hosted service, typically used for premium reasoning, coding, or synthesis tasks.

Examples include models reached through OpenAI, Anthropic, Google Gemini, xAI, AWS Bedrock, and Azure OpenAI.

### Teacher Model

A frontier model used specifically as a source of high-value supervision, critique, judging, or synthesis for the learning loop.

All teacher models are frontier models, but not all frontier-model invocations are teacher uses.

### Provider

A concrete runtime backend or platform through which a model is accessed.

Examples:

- OpenAI direct API
- Anthropic direct API
- Google Gemini direct API
- xAI direct API
- AWS Bedrock-hosted model access
- Azure OpenAI deployment
- local Ollama runtime

### Provider Family

A normalized grouping for related providers and hosted variants.

Examples:

- OpenAI
- Anthropic
- Google Gemini
- xAI
- AWS Bedrock
- Azure OpenAI
- local runtime

### Local Model

A model executed on user-controlled local or self-hosted infrastructure rather than a remote frontier service.

### Local Specialist

A local model or adapter promoted for a narrow domain because it offers acceptable quality with materially better value-per-dollar, privacy, or workflow fit than a designated frontier baseline.

### Session

A sequence of related user interactions that share routing context such as task intent, budget, privacy mode, and prior-turn history.

### Session-Aware Routing

Routing that considers both the current request and accumulated session context when selecting a model or provider.

### Eligible Traffic

Requests that satisfy the routing-policy rules for a given local specialist, benchmark cohort, or experimental route.

### Routing Policy

The explicit, versioned decision logic that ranks candidate models and selects the route for a request or session.

### Fallback

A policy-driven re-route to an alternate provider or model after degradation, timeout, incompatibility, or explicit routing override.

### Designated Frontier Baseline

The named frontier comparison target or target set used to evaluate whether a local specialist is good enough for promotion in a specific domain.

### Value-Per-Dollar

A normalized measure of delivered quality divided by total task cost, used to compare frontier and local routes within a domain.

### Avoided Frontier Spend

Estimated remote-provider cost that would have been incurred if an eligible request had been served by its designated frontier baseline instead of the chosen local specialist.

### Blended Cost

The total cost of serving a traffic slice, including frontier inference, local inference, training amortization, evaluation overhead, and infrastructure overhead where included by policy.

### Quality Delta vs Frontier

The measured difference between a local specialist’s domain score and the designated frontier baseline score for the same evaluation cohort.

### Promotion

The act of moving a trained model from evaluated candidate status into an approved or production-eligible serving state.

### Rollback

The restoration of a prior serving model and routing policy after failure, degradation, or economic underperformance.
