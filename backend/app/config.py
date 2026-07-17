from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    root_dir: Path
    data_dir: Path
    generated_dir: Path
    openai_api_key: str | None
    openai_model: str
    openai_base_url: str
    frontend_origins: tuple[str, ...]
    workspace_root: Path

    @classmethod
    def from_env(cls) -> "Settings":
        backend_root = Path(__file__).resolve().parent.parent
        project_root = backend_root.parent
        data = Path(os.getenv("AGENT_MANAGER_DATA_DIR", "backend/data"))
        generated = Path(os.getenv("AGENT_MANAGER_GENERATED_DIR", "backend/generated_tools"))
        return cls(
            root_dir=project_root,
            data_dir=data if data.is_absolute() else project_root / data,
            generated_dir=generated if generated.is_absolute() else project_root / generated,
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            frontend_origins=tuple(
                origin.strip()
                for origin in os.getenv(
                    "AGENT_MANAGER_FRONTEND_ORIGINS",
                    "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173",
                ).split(",")
                if origin.strip()
            ),
            workspace_root=Path(os.getenv("AGENT_MANAGER_WORKSPACE_ROOT", str(project_root))).resolve(),
        )
