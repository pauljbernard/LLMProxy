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
4. Open `Candidates, Datasets & Training`
5. Approve the new candidate
6. Create an export for that domain
7. Use the export row action to fill the dataset import form
8. Run dataset import
9. Use the dataset version row action to fill the training form
10. Run training
11. Use the training row action to fill the evaluation form
12. Run evaluation
13. Open `Evaluation & KPI`
14. Use the evaluation row action to prepare deployment

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
- evaluation and KPI information available through the admin console and APIs

## Where the records live

- candidates and exports: `proxy` schema
- dataset import, dataset version, training run, evaluation run: `learner` schema
- jobs, events, performance, routing policy versions: `integration` schema
