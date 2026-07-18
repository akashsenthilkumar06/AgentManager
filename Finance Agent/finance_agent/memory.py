"""Small, inspectable local JSON memory store."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from .state import MEMORY_PATH


class LocalMemory:
    def _read(self) -> list[dict[str, Any]]:
        if not MEMORY_PATH.exists():
            return []
        try:
            return json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def save(self, company: str, ticker: str | None, result: dict[str, Any]) -> None:
        items = self._read()
        items.append({"created_at": datetime.now(timezone.utc).isoformat(), "company": company,
                      "ticker": ticker, "summary": result.get("summary"),
                      "metrics": result.get("metrics"), "risk_score": result.get("risk_score")})
        MEMORY_PATH.write_text(json.dumps(items[-100:], indent=2, default=str), encoding="utf-8")

    def history(self, company: str) -> list[dict[str, Any]]:
        return [item for item in self._read() if item.get("company", "").lower() == company.lower()]
