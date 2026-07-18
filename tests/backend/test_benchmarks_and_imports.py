"""Paired benchmark and imported-agent integration coverage."""

from __future__ import annotations

import json
import shlex
import sys
import time


def metric(run: dict, metric_id: str) -> dict:
    return next(
        item for item in run["metrics"] if item["id"] == metric_id
    )


def test_benchmark_reports_measured_parity_then_manager_uplift(client):
    baseline_response = client.post(
        "/api/benchmarks",
        json={"agent_id": "finance-agent"},
    )

    assert baseline_response.status_code == 200
    baseline_run = baseline_response.json()
    assert baseline_run["status"] == "completed"
    assert baseline_run["scenarios"]
    assert metric(baseline_run, "overall_score")["baseline"] == 100
    assert metric(baseline_run, "overall_score")["managed"] == 100
    assert "equally" in baseline_run["summary"]
    assert any(
        "No OpenAI call" in item
        for item in baseline_run["evidence"]
    )

    build = client.post(
        "/api/builds",
        json={
            "prompt": (
                "Build a finance tool that checks invoice status and "
                "summarizes payment risk."
            ),
            "agent_id": "finance-agent",
            "deploy": True,
        },
    )
    assert build.status_code == 200
    assert build.json()["decision"] == "build"

    managed_response = client.post(
        "/api/benchmarks",
        json={"agent_id": "finance-agent"},
    )
    assert managed_response.status_code == 200
    managed_run = managed_response.json()
    score = metric(managed_run, "overall_score")
    assert score["managed"] > score["baseline"]
    added_scenario = next(
        scenario
        for scenario in managed_run["scenarios"]
        if scenario["required_tool"] == "invoice_status_summary"
    )
    assert added_scenario["baseline"]["status"] == "unavailable"
    assert added_scenario["managed"]["status"] == "passed"
    assert added_scenario["managed"]["provider"] == "manager_runtime"
    assert added_scenario["managed"]["output_keys"]

    history = client.get(
        "/api/benchmarks",
        params={"agent_id": "finance-agent"},
    )
    assert history.status_code == 200
    assert [item["id"] for item in history.json()][:2] == [
        managed_run["id"],
        baseline_run["id"],
    ]


def test_imported_agent_is_indexed_readable_and_runnable(
    client,
    tmp_path,
):
    import backend.app.dependencies as dependencies

    project = tmp_path / "real-agent"
    project.mkdir()
    (project / "README.md").write_text(
        "# Real agent\n\nA locally imported support agent for testing.",
        encoding="utf-8",
    )
    (project / "AGENTS.md").write_text(
        "Use evidence from the ultraviolet_protocol before answering.",
        encoding="utf-8",
    )
    (project / "knowledge.py").write_text(
        "ultraviolet_protocol = 'UV-42'\n",
        encoding="utf-8",
    )
    (project / ".env").write_text(
        "OPENAI_API_KEY=must-not-be-indexed\n",
        encoding="utf-8",
    )
    (project / "runner.py").write_text(
        "import time\n"
        "print('IMPORTED_AGENT_READY', flush=True)\n"
        "while True:\n"
        "    time.sleep(0.1)\n",
        encoding="utf-8",
    )
    run_command = (
        f"{shlex.quote(sys.executable)} -u runner.py"
    )

    response = client.post(
        "/api/managed-agents/import",
        json={
            "path": str(project),
            "name": "Real Local Agent",
            "run_command": run_command,
        },
    )

    assert response.status_code == 200
    imported = response.json()
    agent = imported["agent"]
    assert imported["already_imported"] is False
    assert imported["profile"]["indexed_files"] == 4
    assert imported["profile"]["languages"] == [
        "markdown",
        "python",
    ]
    assert run_command in agent["detected_entrypoints"] or (
        agent["run_command"] == run_command
    )
    assert agent["imported"] is True
    assert agent["workspace_root"] == str(project.resolve())
    assert agent["run_command"] == run_command

    workspace = dependencies.managed_workspace.inspect(
        dependencies.store.architecture().agents[-1],
        query="ultraviolet_protocol",
    )
    assert workspace["connected_workspace"]["root_path"] == str(
        project.resolve()
    )
    context = next(
        item
        for item in workspace["context_files"]
        if item["path"] == "knowledge.py"
    )
    assert "UV-42" in context["content"]
    assert all(
        ".env" not in item["path"]
        for item in workspace["context_files"]
    )

    manager_file = (
        dependencies.store.path.parent
        / "managed_workspaces"
        / agent["id"]
        / "agent.json"
    )
    manager_config = json.loads(
        manager_file.read_text(encoding="utf-8")
    )
    assert manager_config["workspace_root"] == str(project.resolve())
    assert manager_config["run_command"] == run_command

    start = client.post(
        f"/api/managed-agents/{agent['id']}/process/start",
        json={},
    )
    assert start.status_code == 200
    assert start.json()["status"] == "running"
    assert start.json()["pid"]

    status = start.json()
    for _ in range(30):
        status = client.get(
            f"/api/managed-agents/{agent['id']}/process"
        ).json()
        if any(
            "IMPORTED_AGENT_READY" in line
            for line in status["logs"]
        ):
            break
        time.sleep(0.02)
    assert any(
        "IMPORTED_AGENT_READY" in line
        for line in status["logs"]
    )

    stopped = client.post(
        f"/api/managed-agents/{agent['id']}/process/stop",
        json={},
    )
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"
    assert stopped.json()["pid"] is None

    repeated = client.post(
        "/api/managed-agents/import",
        json={"path": str(project)},
    )
    assert repeated.status_code == 200
    assert repeated.json()["already_imported"] is True
    assert repeated.json()["agent"]["id"] == agent["id"]


def test_import_and_benchmark_validation_errors_are_actionable(
    client,
    tmp_path,
):
    missing = client.post(
        "/api/managed-agents/import",
        json={"path": str(tmp_path / "missing")},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Agent directory was not found"

    benchmark = client.post(
        "/api/benchmarks",
        json={"agent_id": "unknown-agent"},
    )
    assert benchmark.status_code == 422
    assert benchmark.json()["detail"] == "Managed agent not found"
