"""MCP-callable tool functions and their machine-readable schemas."""
from __future__ import annotations
from typing import Any
from .models import AnalysisRequest
from .data_loader import load_data
from .analysis_engine import calculate_metrics
from .valuation import calculate_valuation
from .risk import calculate_risk_score
from .agent import FinanceAnalyst

REQUEST_SCHEMA = {"type": "object", "properties": {"company_name": {"type": "string"}, "ticker": {"type": "string"}, "dataset_path": {"type": "string"}, "question": {"type": "string"}}}
TOOL_DEFINITIONS = [
 {"name": "finance.analyze_company", "description": "Run the autonomous end-to-end financial analysis pipeline.", "inputSchema": REQUEST_SCHEMA},
 {"name": "finance.calculate_metrics", "description": "Calculate growth, profitability, liquidity, leverage, cash-flow, and efficiency metrics.", "inputSchema": REQUEST_SCHEMA},
 {"name": "finance.run_valuation", "description": "Run DCF scenarios and comparable valuation multiples.", "inputSchema": REQUEST_SCHEMA},
 {"name": "finance.assess_risk", "description": "Produce a 0-100 evidence-led financial risk assessment.", "inputSchema": REQUEST_SCHEMA},
 {"name": "finance.generate_report", "description": "Generate a validated analysis report.", "inputSchema": REQUEST_SCHEMA},]

def invoke(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    req = AnalysisRequest.model_validate(arguments)
    if name in {"finance.analyze_company", "finance.generate_report"}: return FinanceAnalyst().analyze(req).model_dump()
    data = load_data(req.dataset_path, req.ticker)
    metrics = calculate_metrics(data)
    if name == "finance.calculate_metrics": return {"metrics": metrics, "evidence": data.evidence}
    if name == "finance.run_valuation": return {"valuation": calculate_valuation(data), "evidence": data.evidence}
    if name == "finance.assess_risk": return {"risk_score": calculate_risk_score(metrics), "evidence": data.evidence}
    raise ValueError(f"Unknown tool: {name}")
