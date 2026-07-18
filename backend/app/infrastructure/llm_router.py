from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from backend.app.core.models import ReuseCandidate


@dataclass(slots=True)
class RouteDecision:
    intent: str
    rationale: str
    provider: str


class LLMRouter:
    """Optional OpenAI reasoning call with a resilient local routing fallback."""

    def __init__(self, api_key: str | None, model: str, base_url: str):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    async def route(self, prompt: str, candidates: list[ReuseCandidate]) -> RouteDecision:
        local = self._local_route(prompt)
        if not self.api_key:
            return local

        context = [
            {"kind": item.kind, "id": item.id, "name": item.name, "description": item.description}
            for item in candidates[:8]
        ]
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["intent", "rationale"],
            "properties": {
                "intent": {"type": "string", "enum": ["order_status", "inventory_risk", "finance_review", "code_review"]},
                "rationale": {"type": "string"},
            },
        }
        body = {
            "model": self.model,
            "instructions": (
                "You route capability requests for an enterprise agent-tool manager. "
                "Choose the closest supported MVP intent using the indexed architecture. "
                "Never invent endpoints or return source code."
            ),
            "input": json.dumps({"request": prompt, "available_components": context}),
            "text": {"format": {"type": "json_schema", "name": "capability_route", "strict": True, "schema": schema}},
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    f"{self.base_url}/responses",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=body,
                )
                response.raise_for_status()
            parsed = json.loads(self._output_text(response.json()))
            return RouteDecision(intent=parsed["intent"], rationale=parsed["rationale"], provider=f"openai:{self.model}")
        except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as exc:
            return RouteDecision(intent=local.intent, rationale=f"Local fallback after provider error: {exc}", provider="local:fallback")

    @staticmethod
    def _output_text(payload: dict[str, object]) -> str:
        direct = payload.get("output_text")
        if isinstance(direct, str):
            return direct
        for output in payload.get("output", []):  # type: ignore[union-attr]
            if not isinstance(output, dict):
                continue
            for content in output.get("content", []):
                if isinstance(content, dict) and content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    return content["text"]
        raise ValueError("OpenAI response did not contain output text")

    @staticmethod
    def _local_route(prompt: str) -> RouteDecision:
        lowered = prompt.lower()
        if any(word in lowered for word in ("finance", "invoice", "billing", "payment")):
            intent = "finance_review"
        elif any(word in lowered for word in ("code", "repo", "review", "test", "bug", "build", "release")):
            intent = "code_review"
        elif any(word in lowered for word in ("inventory", "stock", "sku", "availability")):
            intent = "inventory_risk"
        else:
            intent = "order_status"
        return RouteDecision(
            intent=intent,
            rationale="Matched the request to the closest supported demo capability using architecture keywords.",
            provider="local:deterministic",
        )
