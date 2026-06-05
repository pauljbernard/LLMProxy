# Admin CLI

`llmProxy` includes a utilitarian admin CLI for inspection and operation.

Run it as:

```bash
python3 -m app.cli --help
```

or, if installed:

```bash
llmproxy-admin --help
```

## Common commands

### Health and config

```bash
python3 -m app.cli health
python3 -m app.cli config show
python3 -m app.cli config validate
python3 -m app.cli config set LLMPROXY_OPENAI_API_KEY your-key --env-file .env.local
```

### Proxy operations

```bash
python3 -m app.cli proxy chat --session-id sess_1 --message "user:hello"
python3 -m app.cli proxy ensemble --session-id sess_1 --message "user:compare providers"
python3 -m app.cli proxy embeddings text-embedding-3-small "hello world"
python3 -m app.cli proxy requests list --limit 10
```

### Models and deployment

```bash
python3 -m app.cli models list --proxy
python3 -m app.cli models local
python3 -m app.cli deploy policies
python3 -m app.cli deploy activate coding-lora-1 production
python3 -m app.cli deploy rollback coding-lora-1
```

### Learning loop

```bash
python3 -m app.cli candidates list
python3 -m app.cli candidates approve cand_123
python3 -m app.cli exports run coding --name coding-adapter
python3 -m app.cli datasets imports
python3 -m app.cli datasets versions
python3 -m app.cli training list
python3 -m app.cli evaluation list
```

### Runtime operations

```bash
python3 -m app.cli jobs list
python3 -m app.cli jobs show job_123
python3 -m app.cli events list --verbose
python3 -m app.cli scheduler run-once
python3 -m app.cli jobs run-once
python3 -m app.cli kpis show
```

## When to prefer the CLI

Use the CLI when you want:

- reproducible operator commands
- terminal-friendly JSON output
- scriptable workflows
- quick diagnostics without opening the browser console
