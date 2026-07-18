# Managed agents

This directory contains independent agents that are distributed with Agent
Manager for realistic fleet operation. They live in the same repository for
organization, but each runs as its own process and communicates with the
control plane through MCP.

## Bundled agents

- `finance_agent/` is a financial-analysis service with real dataset loading,
  calculations, risk analysis, valuation, reporting, memory, and an HTTP MCP
  endpoint.

Each agent owns its dependencies, state, environment, and launch instructions.
Do not import these packages into `backend/`; add them from the Managed agents
page so the control plane uses the same directory, process, and MCP boundaries
as it would for an independently deployed client agent.
