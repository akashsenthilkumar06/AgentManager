# Standalone external MCP agent

This directory is an independent FastAPI application. It imports no code from
the main Agent Manager and can run in its own environment or process.

It implements the same MCP subset as the main demo gateway:

- `initialize`
- `tools/list`
- `tools/call`

The server exposes:

- `support.lookup_ticket`
- `support.estimate_resolution`

Responses contain `source: standalone-external-agent` and a `LIVE-MCP-*` proof
value so a live tool call is easy to distinguish from the main app's mock data.

## Run

Using the repository environment:

```bash
cd external_agent
../.venv/bin/python app.py
```

Or install it independently:

```bash
cd external_agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python app.py
```

The default MCP endpoint is:

```text
http://127.0.0.1:8100/mcp
```

Override the bind address with `EXTERNAL_AGENT_HOST` and
`EXTERNAL_AGENT_PORT`.

## Direct protocol checks

```bash
curl -s http://127.0.0.1:8100/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'

curl -s http://127.0.0.1:8100/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'

curl -s http://127.0.0.1:8100/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"support.lookup_ticket","arguments":{"ticket_id":"TCK-9001"}}}'
```
