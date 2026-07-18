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

- Folder: select `managed_agents/finance_agent` in the Finder picker
- Run command: leave blank to detect `.venv/bin/python app.py`
- MCP endpoint: `http://127.0.0.1:8080/mcp`

Bare `python app.py` is also supported: Agent Manager resolves it through the
selected workspace's `.venv` when one is available. Both forms start the same
HTTP MCP service on port `8080` (override with `FINANCE_AGENT_PORT`).

The Finance Agent remains a separate child process even though its source is
kept inside this repository. **Start & Discover**, Test mode, and benchmarks
can launch that process automatically from its saved command, so a second
terminal is not required. Agent Manager still discovers and calls it through
the same HTTP MCP boundary used for any external managed agent.

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

### Supabase database invoices

The `finance.query_invoices` tool performs a bounded, read-only PostgREST query
against `SUPABASE_FINANCE_TABLE` (default: `finance_invoices`). It accepts an
exact `status`, an exact `invoice_id`, and a limit from 1 to 100. It does not
accept raw SQL, arbitrary table names, or arbitrary filter expressions.

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"finance.query_invoices","arguments":{"status":"past_due","limit":25}}}
```

Successful results identify `supabase://database/finance_invoices` as their
source and include the returned rows, result count, amount total, filters,
Content-Range, retrieval time, and an explicit `pulled_live` evidence flag.

Local agent memory is stored in `state/memory.json` (override with `FINANCE_AGENT_STATE_DIR`).
