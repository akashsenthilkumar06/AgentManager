"""Explicit local process controls for imported agent workspaces."""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AgentProcess:
    agent_id: str
    command: str
    cwd: Path
    process: subprocess.Popen[str]
    started_at: str
    stop_requested: bool = False
    logs: deque[str] = field(
        default_factory=lambda: deque(maxlen=240)
    )


class AgentProcessManager:
    """Runs only an explicitly selected command, without a shell."""

    def __init__(self):
        self._processes: dict[str, AgentProcess] = {}
        self._lock = threading.RLock()

    def start(
        self,
        agent_id: str,
        command: str,
        cwd: Path,
    ) -> dict[str, Any]:
        args = shlex.split(command)
        if not args:
            raise ValueError("Run command is empty")
        with self._lock:
            current = self._processes.get(agent_id)
            if current and current.process.poll() is None:
                raise ValueError("Agent process is already running")
            process = subprocess.Popen(
                args,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            record = AgentProcess(
                agent_id=agent_id,
                command=command,
                cwd=cwd,
                process=process,
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            self._processes[agent_id] = record
            thread = threading.Thread(
                target=self._capture_logs,
                args=(record,),
                daemon=True,
                name=f"agent-log-{agent_id}",
            )
            thread.start()
            return self.status(agent_id)

    def stop(self, agent_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._processes.get(agent_id)
            if record is None:
                raise ValueError("Agent process has not been started")
            if record.process.poll() is None:
                record.stop_requested = True
                self._signal_process_group(
                    record,
                    signal.SIGTERM,
                )
                try:
                    record.process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    self._signal_process_group(
                        record,
                        signal.SIGKILL,
                    )
                    record.process.wait(timeout=2)
            return self.status(agent_id)

    def status(self, agent_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._processes.get(agent_id)
            if record is None:
                return {
                    "agent_id": agent_id,
                    "status": "stopped",
                    "pid": None,
                    "command": None,
                    "started_at": None,
                    "exit_code": None,
                    "logs": [],
                }
            exit_code = record.process.poll()
            return {
                "agent_id": agent_id,
                "status": (
                    "running"
                    if exit_code is None
                    else (
                        "stopped"
                        if exit_code == 0 or record.stop_requested
                        else "failed"
                    )
                ),
                "pid": (
                    record.process.pid
                    if exit_code is None
                    else None
                ),
                "command": record.command,
                "started_at": record.started_at,
                "exit_code": exit_code,
                "logs": list(record.logs),
            }

    def stop_all(self) -> None:
        for agent_id in list(self._processes):
            try:
                self.stop(agent_id)
            except (OSError, ValueError):
                continue

    @staticmethod
    def _capture_logs(record: AgentProcess) -> None:
        if record.process.stdout is None:
            return
        for line in record.process.stdout:
            record.logs.append(line.rstrip()[:2000])

    @staticmethod
    def _signal_process_group(
        record: AgentProcess,
        process_signal: signal.Signals,
    ) -> None:
        try:
            os.killpg(record.process.pid, process_signal)
        except (ProcessLookupError, PermissionError):
            if process_signal == signal.SIGKILL:
                record.process.kill()
            else:
                record.process.terminate()
