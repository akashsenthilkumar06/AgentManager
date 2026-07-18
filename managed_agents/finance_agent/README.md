# Finance Analyst Agent

An independent Python 3.12 financial-analysis service bundled inside Agent
Manager. It has no backend imports or shared runtime dependency and exposes an
MCP-style JSON-RPC endpoint at `POST /mcp`.

## Run

From the Agent Manager repository root:

```bash
python3 -m venv managed_agents/finance_agent/.venv
managed_agents/finance_agent/.venv/bin/pip install -r managed_agents/finance_agent/requirements.txt
managed_agents/finance_agent/.venv/bin/uvicorn finance_agent.app:app \
  --app-dir managed_agents --host 127.0.0.1 --port 8080
```

Health: `GET http://127.0.0.1:8080/health`.

To manage it in the UI, open **Managed agents**, choose **Add agent**, and use:

- Directory: the absolute path to `managed_agents/finance_agent`
- Run command: `.venv/bin/uvicorn finance_agent.app:app --app-dir .. --host 127.0.0.1 --port 8080`
- MCP endpoint: `http://127.0.0.1:8080/mcp`

The Finance Agent remains a separate process even though its source is kept
inside this repository. This lets Agent Manager inspect, start, stop, discover,
and call it through the same boundaries used for any external managed agent.

## MCP example

```json
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"finance.analyze_company","arguments":{"company_name":"Apple","ticker":"apple","question":"Assess financial health"}}}
```

Supported MCP methods are `initialize`, `tools/list`, and `tools/call`. Tool calls return `structuredContent`, an execution trace, verification metadata, evidence, stated limitations, and deterministic calculations suitable for benchmark comparison.

## Input data

`dataset_path` can point to a CSV, JSON, Excel workbook, Parquet file, or a directory containing any combination. Column names are normalized automatically. Without a path, the bundled `demo_data/<ticker>` directory is used. The included demo data is illustrative and not investment advice.

### Supabase Storage dataset

Upload the dataset file to a Supabase Storage bucket, then provide it as the request's `dataset_path`:

```json
{"dataset_path":"supabase://financial-data/apple/income_statement.csv"}
```

Set these variables in the process that starts the agent (do not put secrets in requests or source control):

```bash
export SUPABASE_URL="https://YOUR_PROJECT.supabase.co"
export SUPABASE_SECRET_KEY="sb_secret_..."
managed_agents/finance_agent/.venv/bin/uvicorn finance_agent.app:app \
  --app-dir managed_agents --host 127.0.0.1 --port 8080
```

Alternatively, copy `.env.example` to `.env` in this directory and put the
values there. The service loads this local, Git-ignored file at startup. Keep
`.env.example` as placeholders only.

The secret key is required for private buckets. A public bucket can be read with `SUPABASE_URL` alone. The URI supports CSV, JSON, Excel, and Parquet objects. For a single-file upload, use `demo_data/apple/apple_financials.csv`, `demo_data/tesla/tesla_financials.csv`, or `demo_data/microsoft/microsoft_financials.csv`.

Local agent memory is stored in `state/memory.json` (override with `FINANCE_AGENT_STATE_DIR`).
