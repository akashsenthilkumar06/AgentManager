"""Shared OpenAI Responses API transport and diagnostics."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


@dataclass(slots=True)
class OpenAIProviderError(Exception):
    message: str
    status_code: int | None = None
    request_id: str | None = None

    def __str__(self) -> str:
        return self.message


class OpenAIProvider:
    """Keeps auth, request defaults, retries, and status in one place."""

    RETRYABLE_STATUS_CODES = {408, 409, 429}

    def __init__(
        self,
        api_key: str | None,
        model: str,
        base_url: str,
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
        reasoning_effort: str | None = None,
        max_output_tokens: int | None = None,
        timeout_seconds: float = 45.0,
        max_retries: int = 2,
        safety_identifier: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.organization_id = organization_id
        self.project_id = project_id
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.safety_identifier = safety_identifier
        self.transport = transport
        self.last_status = "not_tested"
        self.last_checked_at: str | None = None
        self.last_error: str | None = None
        self.last_request_id: str | None = None
        self.last_response_model: str | None = None

    @property
    def configured(self) -> bool:
        return bool(
            self.api_key
            and self.api_key not in {
                "your_api_key_here",
                "your-key",
            }
        )

    def status(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "status": (
                self.last_status
                if self.configured
                else "not_configured"
            ),
            "model": self.model,
            "response_model": self.last_response_model,
            "base_url": self.base_url,
            "reasoning_effort": self.reasoning_effort,
            "project_configured": bool(self.project_id),
            "organization_configured": bool(
                self.organization_id
            ),
            "last_checked_at": self.last_checked_at,
            "last_error": self.last_error,
            "last_request_id": self.last_request_id,
        }

    def headers(self) -> dict[str, str]:
        if not self.api_key:
            raise OpenAIProviderError(
                "OPENAI_API_KEY is not configured"
            )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.organization_id:
            headers["OpenAI-Organization"] = self.organization_id
        if self.project_id:
            headers["OpenAI-Project"] = self.project_id
        return headers

    def prepare_body(
        self,
        body: dict[str, Any],
        *,
        reasoning_effort: str | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        prepared = dict(body)
        prepared.setdefault("model", self.model)
        prepared.setdefault("store", False)
        effort = (
            reasoning_effort
            if reasoning_effort is not None
            else self.reasoning_effort
        )
        if effort and "reasoning" not in prepared:
            prepared["reasoning"] = {"effort": effort}
        output_limit = (
            max_output_tokens
            if max_output_tokens is not None
            else self.max_output_tokens
        )
        if output_limit and "max_output_tokens" not in prepared:
            prepared["max_output_tokens"] = output_limit
        if (
            self.safety_identifier
            and "safety_identifier" not in prepared
        ):
            prepared["safety_identifier"] = self.safety_identifier
        return prepared

    async def create_response(
        self,
        body: dict[str, Any],
        *,
        client: httpx.AsyncClient | None = None,
        reasoning_effort: str | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        prepared = self.prepare_body(
            body,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
        )
        owns_client = client is None
        active_client = client or httpx.AsyncClient(
            timeout=self.timeout_seconds,
            transport=self.transport,
        )
        try:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await active_client.post(
                        f"{self.base_url}/responses",
                        headers=self.headers(),
                        json=prepared,
                    )
                    request_id = response.headers.get("x-request-id")
                    if self._retryable(response.status_code):
                        if attempt < self.max_retries:
                            await asyncio.sleep(0.25 * (2**attempt))
                            continue
                    if response.is_error:
                        raise self._response_error(
                            response,
                            request_id,
                        )
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise OpenAIProviderError(
                            "OpenAI returned a non-object response",
                            request_id=request_id,
                        )
                    self._record_success(payload, request_id)
                    return payload
                except httpx.TransportError as exc:
                    if attempt < self.max_retries:
                        await asyncio.sleep(0.25 * (2**attempt))
                        continue
                    error = OpenAIProviderError(
                        f"Could not reach OpenAI: {exc}"
                    )
                    self._record_failure(error)
                    raise error from exc
                except OpenAIProviderError as exc:
                    self._record_failure(exc)
                    raise
                except (ValueError, TypeError) as exc:
                    error = OpenAIProviderError(
                        f"OpenAI returned an invalid response: {exc}"
                    )
                    self._record_failure(error)
                    raise error from exc
            raise OpenAIProviderError(
                "OpenAI request exhausted its retry budget"
            )
        finally:
            if owns_client:
                await active_client.aclose()

    async def test_connection(self) -> dict[str, Any]:
        if not self.configured:
            error = OpenAIProviderError(
                "OPENAI_API_KEY is not configured"
            )
            self._record_failure(error)
            raise error
        payload = await self.create_response(
            {
                "instructions": (
                    "This is a provider readiness check. "
                    "Return exactly READY."
                ),
                "input": "Return exactly READY.",
                "text": {"verbosity": "low"},
            },
            reasoning_effort="none",
            max_output_tokens=32,
        )
        output = self.output_text(payload)
        if "READY" not in output.upper():
            error = OpenAIProviderError(
                "OpenAI responded, but the readiness output was unexpected",
                request_id=self.last_request_id,
            )
            self._record_failure(error)
            raise error
        return self.status()

    @staticmethod
    def output_text(payload: dict[str, Any]) -> str:
        direct = payload.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        for item in payload.get("output", []):
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if (
                    isinstance(content, dict)
                    and content.get("type") == "output_text"
                    and isinstance(content.get("text"), str)
                ):
                    return content["text"].strip()
        raise OpenAIProviderError(
            "OpenAI response did not contain output text"
        )

    def _record_success(
        self,
        payload: dict[str, Any],
        request_id: str | None,
    ) -> None:
        self.last_status = "connected"
        self.last_checked_at = self._now()
        self.last_error = None
        self.last_request_id = request_id
        response_model = payload.get("model")
        self.last_response_model = (
            response_model
            if isinstance(response_model, str)
            else self.last_response_model
        )

    def _record_failure(self, error: OpenAIProviderError) -> None:
        self.last_status = "error"
        self.last_checked_at = self._now()
        self.last_error = error.message
        self.last_request_id = error.request_id

    def _retryable(self, status_code: int) -> bool:
        return (
            status_code in self.RETRYABLE_STATUS_CODES
            or status_code >= 500
        )

    @staticmethod
    def _response_error(
        response: httpx.Response,
        request_id: str | None,
    ) -> OpenAIProviderError:
        message = f"OpenAI request failed with HTTP {response.status_code}"
        try:
            payload = response.json()
            detail = payload.get("error", {})
            candidate = (
                detail.get("message")
                if isinstance(detail, dict)
                else None
            )
            if isinstance(candidate, str) and candidate.strip():
                message = candidate.strip()
        except ValueError:
            pass
        return OpenAIProviderError(
            message=message,
            status_code=response.status_code,
            request_id=request_id,
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
