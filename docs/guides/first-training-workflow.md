# First Training Workflow

This guide walks one operator through the core learning loop:

1. candidate
2. export
3. dataset import
4. training
5. evaluation
6. deployment preparation

## Option 1: use the operator console

Open:

```text
http://127.0.0.1:8000/admin
```

Then:

1. Enter token `change-me`
2. Open `Proxy`
3. Run a chat request with:
   - session id
   - domain hint such as `coding`
   - task type hint such as `code_review`
4. Open `Data Pipeline`
5. Approve the new candidate
6. Create an export for that domain
7. Use the export row action to fill the dataset import form
8. Run dataset import
9. Use the dataset version row action to fill the training form
10. Open `Training > Runs & Evaluation`
11. Run training
12. Use the training row action to fill the evaluation form
13. Run evaluation
14. Open `Models > Deploy` to prepare route exposure or deployment follow-up

## Option 2: use the CLI

Example progression:

```bash
python3 -m app.cli candidates list
python3 -m app.cli candidates approve cand_123
python3 -m app.cli exports run coding --name coding-adapter --min-quality-score 0.5
python3 -m app.cli datasets import dsexp_123 /data/exports/file.manifest.json /data/exports/file.jsonl
python3 -m app.cli training run dsv_123 Qwen/Qwen2.5-Coder-7B-Instruct qlora
python3 -m app.cli evaluation run train_123
```

## Expected artifacts

After a successful run, you should see:

- export JSONL and manifest under `/data/exports`
- dataset split files under `/data/datasets`
- training artifacts under `/data/checkpoints`
- model package under `/data/models`
- evaluation information under `Training > Runs & Evaluation`
- KPI and runtime oversight under `Training > Runtime & KPI`

## Why this workflow matters

This workflow is the clearest illustration that `llmProxy` is a training proxy rather than only an inference proxy.

The same control plane that routes production traffic also:

- captures reusable candidate work
- turns approved work into datasets
- runs training and evaluation
- prepares smaller owned specialists to take over appropriate classes of work

That is the mechanism for reducing repeated foundation-model costs while retaining the resulting domain-specific capability as internal intellectual property.

## Real backend note

Training and evaluation now support command-backed execution.

Before expecting a real successful training/evaluation cycle, configure:

- `LLMPROXY_LORA_TRAINER_COMMAND` or `LLMPROXY_QLORA_TRAINER_COMMAND`
- `LLMPROXY_EVALUATION_COMMAND`

If those are not configured, the queued lifecycle still works, but the worker
or evaluation endpoint will fail honestly rather than fabricating results.

For the exact JSON contract and smoke-test adapters, see:

- [Backend Command Integration](./backend-command-integration.md)

## Worker note

In the default Compose deployment, long-running training jobs are intended to
run on the dedicated `training-worker` service so they do not monopolize the
general operational worker.

## Where the records live

- candidates and exports: `proxy` schema
- dataset import, dataset version, training run, evaluation run: `learner` schema
- jobs, events, performance, routing policy versions: `integration` schema
