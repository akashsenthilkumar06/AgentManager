"""Runtime settings; no dependency on any manager repository."""
from __future__ import annotations

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent


def _load_local_env() -> None:
    """Load a simple local .env file without adding a runtime dependency.

    Environment variables set by the host always take precedence. The .env file
    is ignored by Git and is only intended for local service development.
    """
    env_path = PACKAGE_ROOT / ".env"
    if not env_path.exists():
        env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_local_env()
DATA_ROOT = PACKAGE_ROOT / "demo_data"
STATE_ROOT = Path(os.getenv("FINANCE_AGENT_STATE_DIR", PACKAGE_ROOT / "state"))
STATE_ROOT.mkdir(parents=True, exist_ok=True)
MEMORY_PATH = STATE_ROOT / "memory.json"
AGENT_NAME = "Finance Analyst Agent"
AGENT_VERSION = "1.0.0"
