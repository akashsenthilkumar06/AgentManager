# Agent Manager Native

A native macOS SwiftUI app for the Agentic AI Manager backend.

This project is intentionally isolated from the React and Electron clients. It
packages the complete backend source inside `Agent Manager.app`, keeps its
runtime state under `~/Library/Application Support/Agent Manager`, starts its
own backend process on an available local port, and never opens a browser or
loads the React frontend.

Build and open the app from the repository root:

```bash
make app
```

The equivalent direct launcher is `./bin/agent-manager`. Both commands return
after asking macOS to open the app, just like launching it from Finder. The
generated `Agent Manager.app` can also be double-clicked directly.

Requirements:

- macOS 14 or newer
- Xcode command-line tools with Swift 6
- Python 3.11+ with FastAPI, Uvicorn, HTTPX, and python-dotenv installed

The native client supports the same active product surfaces as the website:
dashboard, standing reconciliation findings, Manager and Test workspaces,
managed and imported local agents, scoped process controls, MCP endpoint
discovery, paired benchmarks, conversation evidence, activity, health probes,
OpenAI provider readiness, per-agent model and reasoning controls, the
source-backed Finance Correction demo, and demo reset. Navigation stays in a
compact macOS menu so workspace content uses the full window.

For OpenAI or Supabase-backed runs, copy `.env.example` to `.env` beside
`Agent Manager.app`. Finder launches load that file automatically. You can
instead place the private file at
`~/Library/Application Support/Agent Manager/.env`.

For SwiftUI development without repackaging, run:

```bash
AGENT_MANAGER_PROJECT_ROOT="$PWD" \
AGENT_MANAGER_NATIVE_ROOT="$PWD/AgentManagerNative" \
swift run --package-path AgentManagerNative AgentManagerNative
```
