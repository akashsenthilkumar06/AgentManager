"""Public request and result contracts for the independent finance service."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    company_name: str = "Unknown company"
    ticker: str | None = None
    dataset_path: str | None = None
    question: str = "Provide a financial analysis."


class InvoiceQueryRequest(BaseModel):
    status: str | None = None
    invoice_id: str | None = None
    limit: int = Field(default=25, ge=1, le=100)


class ToolTrace(BaseModel):
    tool: str
    status: Literal["success", "warning", "error"]
    details: str


class AnalysisResult(BaseModel):
    summary: str
    financial_health: dict[str, Any]
    metrics: dict[str, Any]
    valuation: dict[str, Any]
    risk_score: dict[str, Any]
    recommendation: str
    confidence: float
    evidence: list[dict[str, Any]]
    limitations: list[str]
    verification: dict[str, Any]
    tool_trace: list[ToolTrace]
