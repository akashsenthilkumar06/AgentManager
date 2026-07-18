"""OpenAI model choices exposed by the managed-agent configuration UI."""

from __future__ import annotations

from typing import Any


OPENAI_REASONING_EFFORTS = (
    "none",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)

OPENAI_MODEL_OPTIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "gpt-5.6-sol",
        "label": "GPT-5.6 Sol",
        "role": "Frontier",
        "description": (
            "Highest-quality option for difficult, quality-first agent work."
        ),
        "reasoning_efforts": list(OPENAI_REASONING_EFFORTS),
    },
    {
        "id": "gpt-5.6-terra",
        "label": "GPT-5.6 Terra",
        "role": "Balanced",
        "description": (
            "Balanced quality, latency, and cost for everyday agent work."
        ),
        "reasoning_efforts": list(OPENAI_REASONING_EFFORTS),
    },
    {
        "id": "gpt-5.6-luna",
        "label": "GPT-5.6 Luna",
        "role": "Fast",
        "description": (
            "Fast, lower-cost option for routing, extraction, and simpler work."
        ),
        "reasoning_efforts": list(OPENAI_REASONING_EFFORTS),
    },
)

OPENAI_MODEL_IDS = frozenset(
    str(option["id"]) for option in OPENAI_MODEL_OPTIONS
)


def openai_model_catalog() -> list[dict[str, Any]]:
    """Return a JSON-safe copy so API callers cannot mutate the registry."""

    return [
        {
            **option,
            "reasoning_efforts": list(option["reasoning_efforts"]),
        }
        for option in OPENAI_MODEL_OPTIONS
    ]
