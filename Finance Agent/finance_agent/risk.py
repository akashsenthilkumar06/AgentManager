"""Evidence-led, bounded risk scoring."""
from __future__ import annotations
from typing import Any

def calculate_risk_score(metrics: dict[str, Any]) -> dict[str, Any]:
    p, l, lev, growth = metrics.get("profitability", {}), metrics.get("liquidity", {}), metrics.get("leverage", {}), metrics.get("growth", {})
    debt = lev.get("debt_to_equity")
    current = l.get("current_ratio")
    margin = p.get("net_margin")
    revenue_growth = growth.get("revenue_growth_pct")
    components = {"financial_risk": 65 if margin is None else (25 if margin > .15 else 50),
                  "debt_risk": 55 if debt is None else min(100, round(debt * 35)),
                  "liquidity_risk": 50 if current is None else (20 if current >= 1.5 else 65 if current >= 1 else 85),
                  "growth_risk": 50 if revenue_growth is None else (25 if revenue_growth > 5 else 70),
                  "market_risk": 50, "execution_risk": 45}
    score = round(sum(components.values()) / len(components))
    evidence = [f"Debt/equity: {debt}", f"Current ratio: {current}", f"Revenue growth: {revenue_growth}%"]
    return {"score": score, "level": "high" if score >= 67 else "moderate" if score >= 34 else "low", "components": components,
            "explanation": "Score combines balance-sheet, profitability, growth, market, and execution indicators.", "evidence": evidence}
