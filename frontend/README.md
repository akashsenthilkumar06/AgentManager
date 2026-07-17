# Frontend sector

This directory is a standalone React 19 and Vite application. It owns the
browser experience only and contains no agent, persistence, validation, or
generated-code logic.

- `src/App.jsx` contains routed application state.
- `src/pages` contains the shared Agent Workspace, managed-agent directory,
  individual agent/tool workspaces, Activity, and System Health pages.
- `src/layout` contains the shared sidebar shell.
- `src/components/FilterBar.jsx` provides the shared search, filter-chip, result
  count, clear-filter, and view-toggle pattern.
- `src/api.js` owns the configurable backend client.
- `src/styles.css` owns the softer rounded design system, motion, and responsive
  workspace layout.
- `vite.config.js` proxies local API requests to FastAPI on port 8000.

Run `npm run dev` for local development and `npm run build` for a deployable
static bundle. Set `VITE_API_BASE_URL` when the API is hosted on another origin.
FastAPI does not serve this frontend.

The interface is agent-first. Workspace is a full-height conversational
development environment. In Manager mode, the center chat accepts requested
changes, the left rail contains Manager history and the selected client-agent
files, and the right rail shows live MCP tool routing, edits, and validation.
Review mode stages diffs; Auto mode applies validated changes. Test client mode
talks directly to the selected client agent, preserves its history, and expands
verification evidence. The shared motion system includes a
`prefers-reduced-motion` fallback.

Global navigation is hidden behind one floating menu button and opens as a
translucent overlay without resizing the workspace. The active agent is chosen
from a single list control in the studio header rather than a permanent row of
agent cards.

To start both React and FastAPI while your terminal is already inside this
directory, run `make dev`. The local Makefile forwards to the shared project
launcher, so the same command works from either the repository root or
`frontend/`.
