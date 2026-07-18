from __future__ import annotations

import sys
import time

from backend.app.infrastructure.agent_process import AgentProcessManager
from backend.app.infrastructure.workspace_access import WorkspaceAccess


def test_bare_python_prefers_imported_agents_virtual_environment(
    tmp_path,
):
    bin_directory = tmp_path / ".venv" / "bin"
    bin_directory.mkdir(parents=True)
    workspace_python = bin_directory / "python"
    workspace_python.symlink_to(sys.executable)
    (tmp_path / "worker.py").write_text(
        "print('LOCAL_RUNTIME_OK', flush=True)\n",
        encoding="utf-8",
    )

    manager = AgentProcessManager()
    manager.start("local-agent", "python worker.py", tmp_path)

    status = manager.status("local-agent")
    for _ in range(50):
        if status["status"] != "running":
            break
        time.sleep(0.01)
        status = manager.status("local-agent")

    assert status["status"] == "stopped"
    assert status["exit_code"] == 0
    assert any(
        str(workspace_python) in line
        for line in status["logs"]
    )
    assert "LOCAL_RUNTIME_OK" in status["logs"]


def test_python_entrypoint_detection_uses_workspace_runtime(tmp_path):
    bin_directory = tmp_path / ".venv" / "bin"
    bin_directory.mkdir(parents=True)
    (bin_directory / "python").write_text("", encoding="utf-8")
    (tmp_path / "app.py").write_text(
        "print('agent')\n",
        encoding="utf-8",
    )

    profile = WorkspaceAccess(tmp_path).inspect_agent_project(tmp_path)

    assert ".venv/bin/python app.py" in profile[
        "detected_entrypoints"
    ]
