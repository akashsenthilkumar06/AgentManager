from __future__ import annotations

import json
from dataclasses import dataclass

from backend.app.core.models import ReuseCandidate
from backend.app.infrastructure.openai_provider import (
    OpenAIProvider,
    OpenAIProviderError,
)


@dataclass(slots=True)
class RouteDecision:
    intent: str
    rationale: str
    provider: str


class LLMRouter:
    """Optional OpenAI reasoning call with a resilient local routing fallback."""

    def __init__(self, provider: OpenAIProvider):
        self.provider = provider

    async def route(self, prompt: str, candidates: list[ReuseCandidate]) -> RouteDecision:
        local = self._local_route(prompt)
        if not self.provider.configured:
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
            "instructions": (
                "You route capability requests for an enterprise agent-tool manager. "
                "Choose the closest supported MVP intent using the indexed architecture. "
                "Never invent endpoints or return source code."
            ),
            "input": json.dumps({"request": prompt, "available_components": context}),
            "text": {"format": {"type": "json_schema", "name": "capability_route", "strict": True, "schema": schema}},
        }
        try:
            response = await self.provider.create_response(
                body,
                reasoning_effort="none",
                max_output_tokens=320,
            )
            parsed = json.loads(self.provider.output_text(response))
            return RouteDecision(intent=parsed["intent"], rationale=parsed["rationale"], provider=f"openai:{self.provider.model}")
        except (OpenAIProviderError, KeyError, ValueError, json.JSONDecodeError) as exc:
            return RouteDecision(intent=local.intent, rationale=f"Local fallback after provider error: {exc}", provider="local:fallback")

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
