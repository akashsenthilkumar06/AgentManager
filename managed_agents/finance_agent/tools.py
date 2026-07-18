"""MCP-callable tool functions and their machine-readable schemas."""
from __future__ import annotations
from typing import Any
from .models import AnalysisRequest, InvoiceQueryRequest
from .data_loader import load_data
from .analysis_engine import calculate_metrics
from .valuation import calculate_valuation
from .risk import calculate_risk_score
from .agent import FinanceAnalyst
from .supabase_data import query_invoices

REQUEST_SCHEMA = {"type": "object", "properties": {"company_name": {"type": "string"}, "ticker": {"type": "string"}, "dataset_path": {"type": "string"}, "question": {"type": "string"}}}
INVOICE_QUERY_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "description": "Optional exact invoice status such as open, paid, or past_due.",
        },
        "invoice_id": {
            "type": "string",
            "description": "Optional exact invoice identifier.",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 25,
        },
    },
    "additionalProperties": False,
}
TOOL_DEFINITIONS = [
 {"name": "finance.analyze_company", "description": "Run the autonomous end-to-end financial analysis pipeline.", "inputSchema": REQUEST_SCHEMA},
 {"name": "finance.calculate_metrics", "description": "Calculate growth, profitability, liquidity, leverage, cash-flow, and efficiency metrics.", "inputSchema": REQUEST_SCHEMA},
 {"name": "finance.run_valuation", "description": "Run DCF scenarios and comparable valuation multiples.", "inputSchema": REQUEST_SCHEMA},
 {"name": "finance.assess_risk", "description": "Produce a 0-100 evidence-led financial risk assessment.", "inputSchema": REQUEST_SCHEMA},
 {"name": "finance.generate_report", "description": "Generate a validated analysis report.", "inputSchema": REQUEST_SCHEMA},
 {"name": "finance.query_invoices", "description": "Pull live invoice rows from the configured Supabase database using bounded read-only filters.", "inputSchema": INVOICE_QUERY_SCHEMA},
]

def invoke(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "finance.query_invoices":
        request = InvoiceQueryRequest.model_validate(arguments)
        return query_invoices(
            status=request.status,
            invoice_id=request.invoice_id,
            limit=request.limit,
        )
    req = AnalysisRequest.model_validate(arguments)
    if name in {"finance.analyze_company", "finance.generate_report"}: return FinanceAnalyst().analyze(req).model_dump()
    data = load_data(req.dataset_path, req.ticker)
    metrics = calculate_metrics(data)
    if name == "finance.calculate_metrics": return {"metrics": metrics, "evidence": data.evidence}
    if name == "finance.run_valuation": return {"valuation": calculate_valuation(data), "evidence": data.evidence}
    if name == "finance.assess_risk": return {"risk_score": calculate_risk_score(metrics), "evidence": data.evidence}
    raise ValueError(f"Unknown tool: {name}")
