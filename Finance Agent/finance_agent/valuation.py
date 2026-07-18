"""Transparent scenario valuation models; values use the dataset's currency units."""
from __future__ import annotations
from typing import Any
from .data_loader import FinancialData

def calculate_valuation(data: FinancialData, discount_rate: float = 0.10, terminal_growth: float = 0.03) -> dict[str, Any]:
    fcf = (data.latest("operating_cash_flow") or 0) - (data.latest("capex") or 0)
    shares, price = data.latest("shares_outstanding"), data.latest("price")
    eps, income, revenue = data.latest("eps"), data.latest("net_income"), data.latest("revenue")
    growth_values = data.series("revenue")
    growth = (growth_values[-1] / growth_values[-2] - 1) if len(growth_values) > 1 and growth_values[-2] else 0.05
    scenarios = {}
    for label, rate in {"bear": max(growth - .05, -.05), "base": growth, "bull": growth + .05}.items():
        pv = sum(fcf * (1 + rate) ** year / (1 + discount_rate) ** year for year in range(1, 6))
        terminal = fcf * (1 + rate) ** 5 * (1 + terminal_growth) / (discount_rate - terminal_growth)
        equity_value = pv + terminal / (1 + discount_rate) ** 5
        scenarios[label] = {"enterprise_value": round(equity_value, 2), "intrinsic_value_per_share": round(equity_value / shares, 2) if shares else None, "growth_rate": round(rate, 4)}
    market_cap = price * shares if price and shares else None
    return {"intrinsic_value": scenarios["base"]["intrinsic_value_per_share"], "dcf": scenarios,
            "pe_valuation": round(eps * 20, 2) if eps is not None else None,
            "ev_ebitda": None, "price_to_sales": round(market_cap / revenue, 2) if market_cap and revenue else None,
            "assumptions": {"discount_rate": discount_rate, "terminal_growth": terminal_growth, "forecast_years": 5},
            "sensitivity": {"discount_rate_range": [0.08, 0.12], "terminal_growth_range": [0.02, 0.04]},
            "confidence": 0.65 if fcf > 0 and shares else 0.35}
