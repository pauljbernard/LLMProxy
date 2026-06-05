# llmProxy

This repository is currently in the specification phase for a SpecKit-inspired, spec-driven development project.

The primary implementation baseline is documented through a custom SpecKit-aligned specification set in [specs/001-llmproxy-foundation](./specs/001-llmproxy-foundation) and the extended reference library in [docs/specs](./docs/specs/README.md).

Initial source material is [baseline.txt](./baseline.txt).

Future coding agents should begin with the documents in `docs/specs/` before starting implementation.

## Strategic Objectives

The strategic objective of `llmProxy` is to convert repeated high-value frontier-model usage into durable, owned, local capability.

This project exists to:

- provide an OpenAI-compatible proxy for existing tools, agents, IDEs, and CLIs
- route requests across local runtimes and frontier providers based on task, session, privacy, cost, and quality needs
- capture valuable interactions as governed training assets instead of letting them disappear after inference
- train and evaluate domain-specific local specialists that can take over appropriate classes of work
- shift a meaningful share of token usage from expensive frontier inference to cheaper, private, fine-tuned local models where quality remains acceptable
- preserve auditability, rollback, security, and economic discipline throughout that learning loop

The project is not trying to build a frontier foundation model or a full AI ecosystem. It is trying to build one enabling component: a production-capable local-first proxy and learning system that makes specialized model ownership practical.

## Architecture

![llmProxy architecture](docs/assets/architecture-diagram.svg)

## License

This repository is licensed under the Apache License, Version 2.0. See [LICENSE](./LICENSE).
