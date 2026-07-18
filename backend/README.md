# Backend sector

This directory owns orchestration, APIs, agent behavior, validation, storage,
and runtime-generated tools. It is API-only; it does not render or serve the
React dashboard.

The principal boundary is `app/agents`: every agent has one discoverable file.
Agents depend on shared contracts from `app/core` and adapters from
`app/infrastructure`; they do not depend on REST or MCP transport code.

- `app/api` exposes the workspace REST API.
- `app/mcp` exposes specialist agents through JSON-RPC MCP endpoints.
- `app/dependencies.py` constructs and connects all agents.
- `app/infrastructure/mcp_client.py` discovers managed-agent capabilities.
- `app/infrastructure/workspace_access.py` exposes one safe read-only root.
- `app/infrastructure/cloud_data.py` supplies employee agents with either a configured,
  credential-scoped cloud API or a clearly labeled local demo-cloud simulator.
- Set `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, and optionally
  `SUPABASE_FINANCE_TABLE=finance_invoices` to run the source-backed Finance
  Correction demo. Keep the secret key only in the backend environment.
- `data` contains ignored runtime state.
- `generated_tools` contains validated generated implementations.
