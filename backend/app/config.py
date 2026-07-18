from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


REASONING_EFFORTS = {
    "none",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
}


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None

@dataclass(frozen=True, slots=True)
class Settings:
    root_dir: Path
    data_dir: Path
    generated_dir: Path
    openai_api_key: str | None
    openai_model: str
    openai_base_url: str
    openai_organization_id: str | None
    openai_project_id: str | None
    openai_reasoning_effort: str | None
    openai_max_output_tokens: int
    openai_request_timeout_seconds: float
    openai_max_retries: int
    openai_safety_identifier: str | None
    frontend_origins: tuple[str, ...]
    workspace_root: Path
    reconciliation_interval_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        backend_root = Path(__file__).resolve().parent.parent
        project_root = backend_root.parent
        env_file = os.getenv(
            "AGENT_MANAGER_ENV_FILE",
            str(project_root / ".env"),
        ).strip()
        if env_file:
            load_dotenv(
                Path(env_file).expanduser(),
                override=False,
            )
        data = Path(os.getenv("AGENT_MANAGER_DATA_DIR", "backend/data"))
        generated = Path(os.getenv("AGENT_MANAGER_GENERATED_DIR", "backend/generated_tools"))
        openai_base_url = os.getenv(
            "OPENAI_BASE_URL",
            "https://api.openai.com/v1",
        ).strip().rstrip("/")
        parsed_base_url = urlparse(openai_base_url)
        if (
            parsed_base_url.scheme not in {"http", "https"}
            or not parsed_base_url.netloc
        ):
            raise ValueError(
                "OPENAI_BASE_URL must be an absolute http(s) URL"
            )
        reasoning_effort = _optional_env(
            "OPENAI_REASONING_EFFORT"
        )
        if (
            reasoning_effort is not None
            and reasoning_effort not in REASONING_EFFORTS
        ):
            raise ValueError(
                "OPENAI_REASONING_EFFORT must be one of "
                "none, low, medium, high, xhigh, or max"
            )
        output_tokens = int(
            os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "1600")
        )
        if output_tokens < 64:
            raise ValueError(
                "OPENAI_MAX_OUTPUT_TOKENS must be at least 64"
            )
        timeout_seconds = float(
            os.getenv("OPENAI_REQUEST_TIMEOUT_SECONDS", "45")
        )
        if timeout_seconds < 5:
            raise ValueError(
                "OPENAI_REQUEST_TIMEOUT_SECONDS must be at least 5"
            )
        max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "2"))
        if max_retries < 0 or max_retries > 5:
            raise ValueError(
                "OPENAI_MAX_RETRIES must be between 0 and 5"
            )
        openai_model = os.getenv(
            "OPENAI_MODEL",
            "gpt-5.6-terra",
        ).strip()
        if not openai_model:
            raise ValueError("OPENAI_MODEL cannot be empty")
        return cls(
            root_dir=project_root,
            data_dir=data if data.is_absolute() else project_root / data,
            generated_dir=generated if generated.is_absolute() else project_root / generated,
            openai_api_key=_optional_env("OPENAI_API_KEY"),
            openai_model=openai_model,
            openai_base_url=openai_base_url,
            openai_organization_id=_optional_env(
                "OPENAI_ORGANIZATION_ID"
            ),
            openai_project_id=_optional_env("OPENAI_PROJECT_ID"),
            openai_reasoning_effort=reasoning_effort or "low",
            openai_max_output_tokens=output_tokens,
            openai_request_timeout_seconds=timeout_seconds,
            openai_max_retries=max_retries,
            openai_safety_identifier=_optional_env(
                "OPENAI_SAFETY_IDENTIFIER"
            ),
            frontend_origins=tuple(
                origin.strip()
                for origin in os.getenv(
                    "AGENT_MANAGER_FRONTEND_ORIGINS",
                    "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173",
                ).split(",")
                if origin.strip()
            ),
            workspace_root=Path(os.getenv("AGENT_MANAGER_WORKSPACE_ROOT", str(project_root))).resolve(),
            reconciliation_interval_seconds=max(
                5.0,
                float(
                    os.getenv(
                        "AGENT_MANAGER_RECONCILIATION_INTERVAL_SECONDS",
                        "30",
                    )
                ),
            ),
        )
