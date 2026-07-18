"""End-to-end proof that the Manager can operate an independent agent."""

from __future__ import annotations

import json
import os
import shlex
import socket
import sys


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _independent_agent_source() -> str:
    return """\
from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


TOOLS = [
    {
        "name": "support.lookup_ticket",
        "description": "Return live proof for a support ticket.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["ticket_id"],
            "properties": {"ticket_id": {"type": "string"}},
        },
    }
]


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("content-length", "0"))
        request = json.loads(self.rfile.read(length))
        method = request.get("method")
        if method == "initialize":
            result = {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "independent-proof-agent",
                    "version": "1.0.0",
                },
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = request.get("params", {})
            ticket_id = params.get("arguments", {}).get("ticket_id")
            if params.get("name") != "support.lookup_ticket":
                self._send({
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "error": {"code": -32601, "message": "Unknown tool"},
                })
                return
            output = {
                "ticket_id": ticket_id,
                "status": "verified_live",
                "source": "independent-managed-agent-process",
                "proof": f"PROCESS-MCP-{ticket_id}",
            }
            result = {
                "content": [
                    {"type": "text", "text": json.dumps(output)}
                ],
                "isError": False,
            }
        else:
            self._send({
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32601, "message": "Unsupported method"},
            })
            return
        self._send({
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": result,
        })

    def _send(self, payload):
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"INDEPENDENT_AGENT_READY port={args.port}", flush=True)
    print(
        "MANAGER_SECRET_VISIBLE="
        + str("MANAGER_CONTROL_SECRET" in os.environ),
        flush=True,
    )
    server.serve_forever()
"""


def test_manager_launches_accesses_discovers_calls_and_stops_agent(
    client,
    tmp_path,
    monkeypatch,
):
    runtime_listing = client.post(
        "/mcp/runtime",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        },
    )
    assert runtime_listing.status_code == 200
    assert {
        tool["name"]
        for tool in runtime_listing.json()["result"]["tools"]
    } == {
        "runtime.status",
        "runtime.start",
        "runtime.stop",
        "runtime.discover",
        "runtime.call_tool",
    }

    project = tmp_path / "independent-agent"
    project.mkdir()
    port = _available_port()
    endpoint = f"http://127.0.0.1:{port}/mcp"
    (project / "README.md").write_text(
        "# Independent proof agent\n\n"
        "A separate support MCP agent with inspectable source.",
        encoding="utf-8",
    )
    (project / "AGENTS.md").write_text(
        "Answer support questions only with PROCESS-MCP proof.",
        encoding="utf-8",
    )
    (project / "agent.py").write_text(
        _independent_agent_source(),
        encoding="utf-8",
    )
    (project / "agent.json").write_text(
        json.dumps({"mcp_endpoint": endpoint}),
        encoding="utf-8",
    )
    (project / ".env").write_text(
        "PRIVATE_AGENT_KEY=never-index-this",
        encoding="utf-8",
    )
    outside_secret = tmp_path / "outside_secret.py"
    outside_secret.write_text(
        "EXTERNAL_SECRET = 'must-not-cross-symlink'",
        encoding="utf-8",
    )
    os.symlink(outside_secret, project / "linked_secret.py")
    monkeypatch.setenv(
        "MANAGER_CONTROL_SECRET",
        "must-not-reach-child",
    )
    command = (
        f"{shlex.quote(sys.executable)} -u agent.py --port {port}"
    )

    imported_response = client.post(
        "/api/managed-agents/import",
        json={
            "path": str(project),
            "name": "Independent Proof Agent",
            "run_command": command,
            "mcp_endpoint": endpoint,
        },
    )
    assert imported_response.status_code == 200
    imported = imported_response.json()
    agent_id = imported["agent"]["id"]
    assert imported["process"]["status"] == "stopped"
    assert imported["agent"]["workspace_root"] == str(
        project.resolve()
    )

    operated_response = client.post(
        "/api/manager/message",
        json={
            "agent_id": agent_id,
            "message": (
                "Start this agent, discover its tools, and call "
                "support.lookup_ticket for ticket TCK-4242."
            ),
            "autonomy": "auto",
        },
    )
    assert operated_response.status_code == 200
    manager_message = operated_response.json()["messages"][-1]
    actions = {
        action["tool"]: action
        for action in manager_message["actions"]
    }
    assert {
        "workspace.inspect",
        "runtime.status",
        "runtime.start",
        "runtime.discover",
        "runtime.call_tool",
    }.issubset(actions)
    assert all(
        actions[name]["status"] == "passed"
        for name in (
            "runtime.status",
            "runtime.start",
            "runtime.discover",
            "runtime.call_tool",
        )
    )
    assert manager_message["changes"] == []
    assert manager_message["evaluation"]["status"] == "passed"

    workspace_evidence = actions["workspace.inspect"]["evidence"]
    assert workspace_evidence["access"] == "read_only"
    assert (
        workspace_evidence["workspace"]["root_path"]
        == str(project.resolve())
    )
    assert ".env" not in workspace_evidence["context_files"]
    assert (
        "linked_secret.py"
        not in workspace_evidence["context_files"]
    )
    assert workspace_evidence["secret_paths_excluded"] is True

    start_evidence = actions["runtime.start"]["evidence"]
    assert start_evidence["protocol"] == "MCP JSON-RPC 2.0"
    assert start_evidence["gateway_receipt"]["endpoint"] == (
        "/mcp/runtime"
    )
    assert start_evidence["gateway_receipt"]["call"] == "tools/call"
    assert (
        actions["runtime.status"]["evidence"]["gateway_receipt"][
            "handshake"
        ]
        == ["initialize", "tools/list"]
    )
    assert start_evidence["process"]["status"] == "running"
    assert start_evidence["process"]["pid"]
    assert (
        start_evidence["discovery"]["server_name"]
        == "independent-proof-agent"
    )

    discovery = actions["runtime.discover"]["evidence"][
        "discovery"
    ]
    assert [tool["name"] for tool in discovery["tools"]] == [
        "support.lookup_ticket"
    ]
    tool_call = actions["runtime.call_tool"]["evidence"][
        "tool_call"
    ]
    assert tool_call["provider"] == "agent_mcp"
    assert tool_call["endpoint"] == endpoint
    assert tool_call["arguments"] == {"ticket_id": "TCK-4242"}
    assert (
        tool_call["output"]["source"]
        == "independent-managed-agent-process"
    )
    assert (
        tool_call["output"]["proof"]
        == "PROCESS-MCP-TCK-4242"
    )

    process = client.get(
        f"/api/managed-agents/{agent_id}/process"
    ).json()
    assert process["status"] == "running"
    assert any(
        "INDEPENDENT_AGENT_READY" in line
        for line in process["logs"]
    )
    assert "MANAGER_SECRET_VISIBLE=False" in process["logs"]

    stopped_response = client.post(
        "/api/manager/message",
        json={
            "agent_id": agent_id,
            "message": "Stop and shut down this agent process.",
            "autonomy": "auto",
        },
    )
    assert stopped_response.status_code == 200
    stop_actions = {
        action["tool"]: action
        for action in stopped_response.json()["messages"][-1][
            "actions"
        ]
    }
    assert stop_actions["runtime.stop"]["status"] == "passed"
    assert (
        stop_actions["runtime.stop"]["evidence"]["process"][
            "status"
        ]
        == "stopped"
    )
    assert (
        client.get(
            f"/api/managed-agents/{agent_id}/process"
        ).json()["status"]
        == "stopped"
    )

    denied_response = client.post(
        "/api/manager/message",
        json={
            "agent_id": agent_id,
            "message": "Start this agent again.",
            "autonomy": "review",
        },
    )
    denied_actions = {
        action["tool"]: action
        for action in denied_response.json()["messages"][-1][
            "actions"
        ]
    }
    assert denied_actions["runtime.start"]["status"] == "failed"
    assert "requires Auto permission" in denied_actions[
        "runtime.start"
    ]["detail"]
    assert (
        client.get(
            f"/api/managed-agents/{agent_id}/process"
        ).json()["status"]
        == "stopped"
    )
