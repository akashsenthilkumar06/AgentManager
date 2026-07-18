"""Run the Agent Manager backend and frontend from one terminal."""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def port_available(port: int) -> bool:
    """Return whether an IPv4 localhost port can be bound right now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def available_port(preferred: int, attempts: int = 50) -> int:
    for port in range(preferred, preferred + attempts):
        if port_available(port):
            return port
    raise RuntimeError(f"No open port found between {preferred} and {preferred + attempts - 1}")


def stream_output(name: str, process: subprocess.Popen[str]) -> None:
    """Prefix each child-process line so interleaved output stays readable."""
    if process.stdout is None:
        return
    color = "\033[36m" if name == "backend" else "\033[32m"
    reset = "\033[0m"
    for line in process.stdout:
        print(f"{color}[{name:8}]{reset} {line}", end="", flush=True)


def stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        process.terminate()
    else:
        os.killpg(process.pid, signal.SIGTERM)


def main() -> int:
    if not command_exists("npm"):
        print("npm is required to run the React frontend.", file=sys.stderr)
        return 1
    if not (FRONTEND / "node_modules").exists():
        print("Frontend dependencies are missing. Run: make install", file=sys.stderr)
        return 1

    preferred_backend_port = int(os.getenv("AGENT_MANAGER_BACKEND_PORT", "8000"))
    preferred_frontend_port = int(os.getenv("AGENT_MANAGER_FRONTEND_PORT", "5173"))
    try:
        backend_port = available_port(preferred_backend_port)
        frontend_port = available_port(preferred_frontend_port)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    backend_url = f"http://127.0.0.1:{backend_port}"
    frontend_url = f"http://127.0.0.1:{frontend_port}"

    backend = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.app.main:app",
        "--reload",
        "--host",
        "127.0.0.1",
        "--port",
        str(backend_port),
    ]
    frontend = [
        "npm",
        "run",
        "dev",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        str(frontend_port),
        "--strictPort",
    ]
    popen_options = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "bufsize": 1,
        "start_new_session": os.name != "nt",
    }

    if backend_port != preferred_backend_port:
        print(f"Port {preferred_backend_port} is already in use; using {backend_port} for the backend.")
    if frontend_port != preferred_frontend_port:
        print(f"Port {preferred_frontend_port} is already in use; using {frontend_port} for the frontend.")

    print("Starting Agentic AI Manager…")
    print(f"  Dashboard: {frontend_url}")
    print(f"  API docs: {backend_url}/docs")
    print("Press Ctrl+C to stop both services.\n")

    processes: list[tuple[str, subprocess.Popen[str]]] = []
    try:
        backend_env = os.environ.copy()
        backend_env["AGENT_MANAGER_FRONTEND_ORIGINS"] = ",".join([
            frontend_url,
            f"http://localhost:{frontend_port}",
        ])
        frontend_env = os.environ.copy()
        frontend_env["VITE_API_PROXY_TARGET"] = backend_url
        processes.append(("backend", subprocess.Popen(backend, cwd=ROOT, env=backend_env, **popen_options)))
        processes.append(("frontend", subprocess.Popen(frontend, cwd=FRONTEND, env=frontend_env, **popen_options)))

        threads = [
            threading.Thread(target=stream_output, args=(name, process), daemon=True)
            for name, process in processes
        ]
        for thread in threads:
            thread.start()

        while True:
            for name, process in processes:
                code = process.poll()
                if code is not None:
                    print(f"\n{name.capitalize()} stopped with exit code {code}.")
                    return code
            threading.Event().wait(0.25)
    except KeyboardInterrupt:
        print("\nStopping frontend and backend…")
        return 0
    finally:
        for _, process in processes:
            stop_process(process)
        for _, process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
