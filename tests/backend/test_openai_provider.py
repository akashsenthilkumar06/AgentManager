"""OpenAI environment, transport, and readiness coverage."""

from __future__ import annotations

import json

import httpx

import backend.app.dependencies as dependencies
from backend.app.config import Settings
from backend.app.infrastructure.openai_provider import OpenAIProvider


def test_settings_load_dotenv_without_overriding_shell(
    tmp_path,
    monkeypatch,
):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=from-dotenv",
                "OPENAI_MODEL=gpt-5.6-terra",
                "OPENAI_PROJECT_ID=proj_example",
                "OPENAI_ORGANIZATION_ID=org_example",
                "OPENAI_REASONING_EFFORT=medium",
                "OPENAI_MAX_OUTPUT_TOKENS=2048",
                "OPENAI_REQUEST_TIMEOUT_SECONDS=60",
                "OPENAI_MAX_RETRIES=3",
                "OPENAI_SAFETY_IDENTIFIER=local-test-user",
            ]
        ),
        encoding="utf-8",
    )
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_PROJECT_ID",
        "OPENAI_ORGANIZATION_ID",
        "OPENAI_REASONING_EFFORT",
        "OPENAI_MAX_OUTPUT_TOKENS",
        "OPENAI_REQUEST_TIMEOUT_SECONDS",
        "OPENAI_MAX_RETRIES",
        "OPENAI_SAFETY_IDENTIFIER",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AGENT_MANAGER_ENV_FILE", str(env_file))
    monkeypatch.setenv("OPENAI_MODEL", "shell-model")

    settings = Settings.from_env()

    assert settings.openai_api_key == "from-dotenv"
    assert settings.openai_model == "shell-model"
    assert settings.openai_project_id == "proj_example"
    assert settings.openai_organization_id == "org_example"
    assert settings.openai_reasoning_effort == "medium"
    assert settings.openai_max_output_tokens == 2048
    assert settings.openai_request_timeout_seconds == 60
    assert settings.openai_max_retries == 3
    assert settings.openai_safety_identifier == "local-test-user"


def test_provider_applies_auth_defaults_and_records_readiness():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"x-request-id": "req_readiness_123"},
            json={
                "model": "gpt-5.6-terra-2026-07-01",
                "output_text": "READY",
                "output": [],
            },
        )

    provider = OpenAIProvider(
        "test-secret-key",
        "gpt-5.6-terra",
        "https://api.openai.com/v1",
        organization_id="org_example",
        project_id="proj_example",
        reasoning_effort="low",
        max_output_tokens=1600,
        safety_identifier="local-test-user",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )

    import asyncio

    result = asyncio.run(provider.test_connection())

    assert result["status"] == "connected"
    assert result["response_model"] == "gpt-5.6-terra-2026-07-01"
    assert result["last_request_id"] == "req_readiness_123"
    assert len(requests) == 1
    request = requests[0]
    assert request.headers["authorization"] == "Bearer test-secret-key"
    assert request.headers["openai-organization"] == "org_example"
    assert request.headers["openai-project"] == "proj_example"
    body = json.loads(request.content)
    assert body["model"] == "gpt-5.6-terra"
    assert body["reasoning"] == {"effort": "none"}
    assert body["max_output_tokens"] == 32
    assert body["store"] is False
    assert body["safety_identifier"] == "local-test-user"


def test_provider_treats_example_placeholder_as_unconfigured():
    provider = OpenAIProvider(
        "your_api_key_here",
        "gpt-5.6-terra",
        "https://api.openai.com/v1",
    )

    assert provider.configured is False
    assert provider.status()["status"] == "not_configured"


def test_openai_status_and_test_endpoints_are_explicit(
    client,
    monkeypatch,
):
    status = client.get("/api/openai/status")
    assert status.status_code == 200
    assert status.json()["status"] == "not_configured"
    assert status.json()["configured"] is False

    missing = client.post("/api/openai/test", json={})
    assert missing.status_code == 422
    assert (
        missing.json()["detail"]["message"]
        == "OPENAI_API_KEY is not configured"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"x-request-id": "req_api_test"},
            json={
                "model": "gpt-5.6-terra",
                "output_text": "READY",
                "output": [],
            },
        )

    monkeypatch.setattr(
        dependencies.openai_provider,
        "api_key",
        "configured-test-key",
    )
    monkeypatch.setattr(
        dependencies.openai_provider,
        "transport",
        httpx.MockTransport(handler),
    )
    connected = client.post("/api/openai/test", json={})

    assert connected.status_code == 200
    assert connected.json()["status"] == "connected"
    assert connected.json()["last_request_id"] == "req_api_test"
    health = client.get("/api/health").json()
    assert health["openai"]["status"] == "connected"
