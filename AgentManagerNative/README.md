# Agent Manager Native

A native macOS SwiftUI app for the Agentic AI Manager backend.

This project is intentionally isolated from the React client. In development,
it starts the Agent Manager backend from the repository root on an available
local port, keeps its state under `AgentManagerNative/Runtime`, and never opens
a browser or loads the React frontend.

Build and open the app from the repository root:

```bash
make app
```

The equivalent direct launcher is
`./AgentManagerNative/agent-manager-native`. Both commands stay attached to
the terminal and stop the native app when you press Control-C.

Requirements:

- macOS 14 or newer
- Xcode command-line tools with Swift 6
- Python 3.11+ with FastAPI, Uvicorn, HTTPX, and python-dotenv installed

The native client supports the same active product surfaces as the website:
dashboard, standing reconciliation findings, Manager and Test workspaces,
managed and imported local agents, scoped process controls, MCP endpoint
discovery, paired benchmarks, conversation evidence, activity, health probes,
OpenAI provider readiness, per-agent model and reasoning controls, and demo
reset. Navigation stays in a compact macOS menu so workspace content uses the
full window.

The launcher automatically gives the native backend the repository-root
`.env`, including its OpenAI configuration. Supabase credentials used by the
independent Finance Agent belong in
`managed_agents/finance_agent/.env`; that service loads its own private file
when Agent Manager starts it.

For SwiftUI development without repackaging, run:

```bash
AGENT_MANAGER_PROJECT_ROOT="$PWD" \
AGENT_MANAGER_NATIVE_ROOT="$PWD/AgentManagerNative" \
swift run --package-path AgentManagerNative AgentManagerNative
```

## Manage the bundled Finance Agent

First install its isolated dependencies:

```bash
python3 -m venv managed_agents/finance_agent/.venv
managed_agents/finance_agent/.venv/bin/pip install \
  -r managed_agents/finance_agent/requirements.txt
```

In **Managed agents**, choose **Add Agent** and provide:

- Directory: the absolute path to `managed_agents/finance_agent`
- Run command:
  `.venv/bin/uvicorn finance_agent.app:app --app-dir .. --host 127.0.0.1 --port 8080`
- MCP endpoint: `http://127.0.0.1:8080/mcp`

After import, use **Start Agent**, then **Test & Discover**. A successful
connection advertises six tools. `finance.query_invoices` reads the configured
Supabase Postgres table, while the analysis tools accept explicit
`supabase://<bucket>/<object>` Storage paths.
