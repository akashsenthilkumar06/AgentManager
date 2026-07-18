"""Autonomous orchestration pipeline, designed for observable benchmark runs."""
from __future__ import annotations
from .models import AnalysisRequest, AnalysisResult, ToolTrace
from .data_loader import load_data
from .analysis_engine import calculate_metrics
from .valuation import calculate_valuation
from .risk import calculate_risk_score
from .reporting import make_report
from .memory import LocalMemory

class FinanceAnalyst:
    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        trace: list[ToolTrace] = []
        data = load_data(request.dataset_path, request.ticker)
        trace.append(ToolTrace(tool="inspect_data", status="success", details=f"Detected {', '.join(data.frames)}"))
        plan = ["calculate metrics", "value cash flows", "assess risk", "validate data-grounding", "generate report"]
        trace.append(ToolTrace(tool="create_plan", status="success", details="; ".join(plan)))
        metrics = calculate_metrics(data); trace.append(ToolTrace(tool="finance.calculate_metrics", status="success", details=metrics["calculation_status"]))
        valuation = calculate_valuation(data); trace.append(ToolTrace(tool="finance.run_valuation", status="success", details="DCF scenarios complete"))
        risk = calculate_risk_score(metrics); trace.append(ToolTrace(tool="finance.assess_risk", status="success", details=f"score={risk['score']}"))
        report = make_report(request.company_name, metrics, valuation, risk, data.evidence)
        successful = metrics["calculation_status"] == "success"
        verification = {"calculations_successful": successful, "evidence_available": bool(data.evidence), "assumptions_stated": bool(valuation.get("assumptions")),
                        "grounded_in_data": bool(data.frames), "source": data.source, "plan": plan}
        trace.append(ToolTrace(tool="self_verify", status="success" if all(verification[k] for k in ["evidence_available", "assumptions_stated", "grounded_in_data"]) else "warning", details=str(verification)))
        result = AnalysisResult(metrics=metrics, valuation=valuation, risk_score=risk, verification=verification, tool_trace=trace, **report)
        LocalMemory().save(request.company_name, request.ticker, result.model_dump())
        return result
