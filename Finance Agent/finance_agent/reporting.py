"""Narrative report assembly without hidden model reasoning."""
from __future__ import annotations
from typing import Any

def make_report(company: str, metrics: dict[str, Any], valuation: dict[str, Any], risk: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    margin = metrics.get("profitability", {}).get("net_margin")
    growth = metrics.get("growth", {}).get("revenue_growth_pct")
    risk_score = risk["score"]
    recommendation = "Hold / investigate further" if risk_score >= 60 else "Constructive, subject to valuation and mandate"
    return {"summary": f"{company}: revenue growth is {growth}% and net margin is {margin}; composite risk is {risk_score}/100.",
            "financial_health": {"profitability": metrics.get("profitability"), "liquidity": metrics.get("liquidity"), "leverage": metrics.get("leverage")},
            "recommendation": recommendation, "confidence": round(min(0.9, 0.4 + .05 * len(evidence)), 2),
            "evidence": evidence,
            "limitations": ["Demo or supplied data is not independently audited.", "DCF is highly sensitive to discount and terminal-growth assumptions.", "Market and execution risk need qualitative external research."]}
