"""Deterministic financial metric calculations."""
from __future__ import annotations
from typing import Any
from .data_loader import FinancialData


def _ratio(a: float | None, b: float | None) -> float | None:
    return round(a / b, 4) if a is not None and b not in (None, 0) else None

def _growth(values: list[float]) -> float | None:
    return round((values[-1] / values[-2] - 1) * 100, 2) if len(values) > 1 and values[-2] else None

def calculate_growth(data: FinancialData) -> dict[str, Any]:
    return {"revenue_growth_pct": _growth(data.series("revenue")), "eps_growth_pct": _growth(data.series("eps")),
            "free_cash_flow_growth_pct": _growth([a - b for a, b in zip(data.series("operating_cash_flow"), data.series("capex"))])}

def calculate_profitability(data: FinancialData) -> dict[str, Any]:
    revenue = data.latest("revenue")
    return {"gross_margin": _ratio(data.latest("gross_profit"), revenue), "operating_margin": _ratio(data.latest("operating_income"), revenue),
            "net_margin": _ratio(data.latest("net_income"), revenue), "roe": _ratio(data.latest("net_income"), data.latest("total_equity")),
            "roic": _ratio(data.latest("operating_income"), (data.latest("total_debt") or 0) + (data.latest("total_equity") or 0))}

def calculate_liquidity(data: FinancialData) -> dict[str, Any]:
    ca, cl, cash, inv = data.latest("current_assets"), data.latest("current_liabilities"), data.latest("cash"), data.latest("inventory")
    return {"current_ratio": _ratio(ca, cl), "quick_ratio": _ratio((ca or 0) - (inv or 0), cl), "cash_ratio": _ratio(cash, cl)}

def calculate_leverage(data: FinancialData) -> dict[str, Any]:
    debt, equity, assets = data.latest("total_debt"), data.latest("total_equity"), data.latest("total_assets")
    return {"debt_to_equity": _ratio(debt, equity), "debt_to_assets": _ratio(debt, assets)}

def calculate_cash_flow(data: FinancialData) -> dict[str, Any]:
    ocf, capex = data.latest("operating_cash_flow"), data.latest("capex")
    return {"operating_cash_flow": ocf, "free_cash_flow": (ocf - capex) if ocf is not None and capex is not None else None,
            "cash_conversion": _ratio(ocf, data.latest("net_income"))}

def calculate_efficiency(data: FinancialData) -> dict[str, Any]:
    return {"asset_turnover": _ratio(data.latest("revenue"), data.latest("total_assets"))}

def calculate_metrics(data: FinancialData) -> dict[str, Any]:
    groups = {"growth": calculate_growth(data), "profitability": calculate_profitability(data), "liquidity": calculate_liquidity(data),
              "leverage": calculate_leverage(data), "cash_flow": calculate_cash_flow(data), "efficiency": calculate_efficiency(data)}
    groups["calculation_status"] = "success" if sum(v is not None for g in groups.values() if isinstance(g, dict) for v in g.values()) >= 5 else "partial"
    return groups
