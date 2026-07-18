from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from backend.app.core.models import ReuseCandidate, ToolRecord


@dataclass(slots=True)
class GeneratedArtifact:
    tool: ToolRecord
    source: str
    plan: dict[str, Any]


class DeveloperAgent:
    """Produces constrained, inspectable Python tools from a capability request."""

    @staticmethod
    def propose_instruction_change(
        objective: str,
        current_instructions: str,
        instructions_append: str,
    ) -> dict[str, str]:
        """Prepare one bounded, reversible managed-agent instruction patch."""

        addition = instructions_append.strip()
        if not objective.strip():
            raise ValueError("A change objective is required")
        if not addition:
            raise ValueError("A concrete instruction addition is required")
        marker = "\n\n## Manager change\n"
        after = (
            current_instructions.rstrip() + marker + addition
        ).strip()[:4000]
        if after == current_instructions.strip():
            raise ValueError("The proposed instructions do not change the agent")
        return {
            "objective": objective.strip(),
            "before": current_instructions,
            "after": after,
            "instructions_append": addition,
        }

    def generate(self, prompt: str, candidates: list[ReuseCandidate], intent: str | None = None) -> GeneratedArtifact:
        lowered = prompt.lower()
        if intent == "finance_review" or (intent is None and any(word in lowered for word in ("finance", "invoice", "billing", "payment"))):
            return self._finance(prompt, candidates)
        if intent == "code_review" or (intent is None and any(word in lowered for word in ("code", "repo", "review", "test", "bug", "build", "release"))):
            return self._code_review(prompt, candidates)
        if intent == "inventory_risk" or (intent is None and any(word in lowered for word in ("inventory", "stock", "sku", "availability"))):
            return self._inventory(prompt, candidates)
        return self._order_status(prompt, candidates)

    def _finance(self, prompt: str, candidates: list[ReuseCandidate]) -> GeneratedArtifact:
        endpoint_ids = self._reused_endpoints(candidates, ["invoices-api", "customers-api"])
        slug = "invoice_status_summary"
        spec = {
            "name": slug,
            "description": (
                "Summarizes invoice status, due date, customer context, and "
                "payment risk for finance workflows."
            ),
            "input_schema": {
                "type": "object",
                "required": ["invoice_id"],
                "properties": {"invoice_id": {"type": "string", "description": "Finance invoice identifier"}},
            },
            "output_schema": {
                "type": "object",
                "required": ["invoice_id", "status", "summary", "past_due"],
                "properties": {
                    "invoice_id": {"type": "string"},
                    "status": {"type": "string"},
                    "summary": {"type": "string"},
                    "past_due": {"type": "boolean"},
                },
            },
            "reuses": endpoint_ids,
        }
        source = f'''\
TOOL_SPEC = {repr(spec)}


async def execute(payload, http_get):
    """Return a normalized invoice status summary."""
    invoice_id = str(payload.get("invoice_id", "")).strip().upper()
    if not invoice_id:
        raise ValueError("invoice_id is required")

    invoice = await http_get("/mock/invoices/" + invoice_id)
    customer = await http_get("/mock/customers/" + invoice["customer_id"])
    past_due = invoice["status"] == "past_due"
    summary = (
        "Invoice " + invoice_id + " is " + invoice["status"].replace("_", " ")
        + " for customer tier " + customer["tier"] + ". Due date: " + invoice["due_date"]
        + ". Amount: " + invoice["currency"] + " " + str(invoice["amount"]) + "."
    )

    return {{
        "invoice_id": invoice_id,
        "status": invoice["status"],
        "customer_id": invoice["customer_id"],
        "due_date": invoice["due_date"],
        "amount": invoice["amount"],
        "past_due": past_due,
        "summary": summary,
    }}
'''
        tool = ToolRecord(
            id=slug,
            name=slug,
            description=spec["description"],
            owner="Manager Agent",
            endpoint_ids=endpoint_ids,
            input_schema=spec["input_schema"],
            output_schema=spec["output_schema"],
            generated=True,
            source_file=f"{slug}.py",
            operation="generated",
            probe_input={"invoice_id": "INV-2048"},
        )
        return GeneratedArtifact(tool=tool, source=source, plan=self._plan(prompt, tool, candidates))

    def _code_review(self, prompt: str, candidates: list[ReuseCandidate]) -> GeneratedArtifact:
        endpoint_ids = self._reused_endpoints(candidates, ["codebase-api"])
        slug = "code_health_summary"
        spec = {
            "name": slug,
            "description": "Summarizes repository health and release risk for coding workflows.",
            "input_schema": {
                "type": "object",
                "required": ["repo_id"],
                "properties": {"repo_id": {"type": "string", "description": "Repository identifier"}},
            },
            "output_schema": {
                "type": "object",
                "required": ["repo_id", "status", "summary", "high_risk"],
                "properties": {
                    "repo_id": {"type": "string"},
                    "status": {"type": "string"},
                    "summary": {"type": "string"},
                    "high_risk": {"type": "boolean"},
                },
            },
            "reuses": endpoint_ids,
        }
        source = f'''\
TOOL_SPEC = {repr(spec)}


async def execute(payload, http_get):
    """Return a normalized code health summary."""
    repo_id = str(payload.get("repo_id", "")).strip().upper()
    if not repo_id:
        raise ValueError("repo_id is required")

    repo = await http_get("/mock/codebase/" + repo_id)
    high_risk = repo["status"] == "needs_review" or repo["failing_tests"] > 0
    summary = (
        "Repository " + repo_id + " is " + repo["status"].replace("_", " ")
        + " with coverage at " + str(repo["coverage"]) + "% and "
        + str(repo["failing_tests"]) + " failing tests."
    )

    return {{
        "repo_id": repo_id,
        "status": repo["status"],
        "coverage": repo["coverage"],
        "failing_tests": repo["failing_tests"],
        "open_issues": repo["open_issues"],
        "high_risk": high_risk,
        "summary": summary,
    }}
'''
        tool = ToolRecord(
            id=slug,
            name=slug,
            description=spec["description"],
            owner="Manager Agent",
            endpoint_ids=endpoint_ids,
            input_schema=spec["input_schema"],
            output_schema=spec["output_schema"],
            generated=True,
            source_file=f"{slug}.py",
            operation="generated",
            probe_input={"repo_id": "REPO-1"},
        )
        return GeneratedArtifact(tool=tool, source=source, plan=self._plan(prompt, tool, candidates))

    def _order_status(self, prompt: str, candidates: list[ReuseCandidate]) -> GeneratedArtifact:
        endpoint_ids = self._reused_endpoints(candidates, ["orders-api", "shipments-api"])
        slug = "order_status_summary"
        spec = {
            "name": slug,
            "description": "Combines order and shipment data into a concise fulfillment status summary.",
            "input_schema": {
                "type": "object",
                "required": ["order_id"],
                "properties": {"order_id": {"type": "string", "description": "Enterprise order identifier"}},
            },
            "output_schema": {
                "type": "object",
                "required": ["order_id", "status", "summary", "delayed"],
                "properties": {
                    "order_id": {"type": "string"},
                    "status": {"type": "string"},
                    "summary": {"type": "string"},
                    "delayed": {"type": "boolean"},
                },
            },
            "reuses": endpoint_ids,
        }
        source = f'''\
TOOL_SPEC = {repr(spec)}


async def execute(payload, http_get):
    """Return a normalized order and shipment status summary."""
    order_id = str(payload.get("order_id", "")).strip().upper()
    if not order_id:
        raise ValueError("order_id is required")

    order = await http_get("/mock/orders/" + order_id)
    shipment = await http_get("/mock/shipments/by-order/" + order_id)
    delayed = bool(shipment.get("exception")) or shipment.get("delay_hours", 0) > 0
    if delayed:
        summary = (
            "Order " + order_id + " is " + shipment["status"].replace("_", " ")
            + " with a " + str(shipment.get("delay_hours", 0)) + " hour delay. "
            + str(shipment.get("exception", "Carrier exception reported"))
            + ". Current ETA: " + shipment["eta"] + "."
        )
    else:
        summary = (
            "Order " + order_id + " is " + shipment["status"].replace("_", " ")
            + ". Latest event: " + shipment["latest_event"]
            + ". Expected delivery: " + shipment["eta"] + "."
        )

    return {{
        "order_id": order_id,
        "status": order["status"],
        "shipment_status": shipment["status"],
        "eta": shipment["eta"],
        "carrier": shipment["carrier"],
        "delayed": delayed,
        "delay_hours": shipment.get("delay_hours", 0),
        "summary": summary,
    }}
'''
        tool = ToolRecord(
            id=slug,
            name=slug,
            description=spec["description"],
            owner="Manager Agent",
            endpoint_ids=endpoint_ids,
            input_schema=spec["input_schema"],
            output_schema=spec["output_schema"],
            generated=True,
            source_file=f"{slug}.py",
            operation="generated",
            probe_input={"order_id": "ORD-1042"},
        )
        return GeneratedArtifact(tool=tool, source=source, plan=self._plan(prompt, tool, candidates))

    def _inventory(self, prompt: str, candidates: list[ReuseCandidate]) -> GeneratedArtifact:
        endpoint_ids = self._reused_endpoints(candidates, ["inventory-api"])
        slug = "inventory_risk_summary"
        spec = {
            "name": slug,
            "description": "Checks live availability and explains stockout risk for a SKU.",
            "input_schema": {"type": "object", "required": ["sku"], "properties": {"sku": {"type": "string"}}},
            "output_schema": {
                "type": "object",
                "required": ["sku", "available", "risk", "summary"],
                "properties": {
                    "sku": {"type": "string"},
                    "available": {"type": "integer"},
                    "risk": {"type": "string"},
                    "summary": {"type": "string"},
                },
            },
            "reuses": endpoint_ids,
        }
        source = f'''\
TOOL_SPEC = {repr(spec)}


async def execute(payload, http_get):
    """Return an inventory availability and stockout risk summary."""
    sku = str(payload.get("sku", "")).strip().upper()
    if not sku:
        raise ValueError("sku is required")
    inventory = await http_get("/mock/inventory/" + sku)
    available = inventory["available"]
    risk = "out_of_stock" if available == 0 else ("low" if available < 20 else "normal")
    summary = (
        sku + " has " + str(available) + " units available across "
        + str(inventory["location_count"]) + " locations. Stockout risk is "
        + risk.replace("_", " ") + "."
    )
    return {{"sku": sku, "available": available, "risk": risk, "summary": summary}}
'''
        tool = ToolRecord(
            id=slug,
            name=slug,
            description=spec["description"],
            owner="Manager Agent",
            endpoint_ids=endpoint_ids,
            input_schema=spec["input_schema"],
            output_schema=spec["output_schema"],
            generated=True,
            source_file=f"{slug}.py",
            operation="generated",
            probe_input={"sku": "SKU-RED-42"},
        )
        return GeneratedArtifact(tool=tool, source=source, plan=self._plan(prompt, tool, candidates))

    @staticmethod
    def _reused_endpoints(candidates: list[ReuseCandidate], defaults: list[str]) -> list[str]:
        found = [item.id for item in candidates if item.kind == "endpoint" and item.id in defaults]
        merged: list[str] = []
        for endpoint_id in [*found, *defaults]:
            if endpoint_id not in merged:
                merged.append(endpoint_id)
        return merged

    @staticmethod
    def _plan(prompt: str, tool: ToolRecord, candidates: list[ReuseCandidate]) -> dict[str, Any]:
        return {
            "request": prompt,
            "strategy": "compose_existing_endpoints",
            "new_tool": tool.name,
            "reuse": [
                {"kind": item.kind, "id": item.id, "name": item.name, "reason": item.reason}
                for item in candidates
                if item.id in tool.endpoint_ids or item.kind == "tool"
            ][:5],
            "steps": [
                "Normalize and validate the tool input",
                "Call the existing architecture endpoints",
                "Combine the responses into a stable output contract",
                "Validate statically and against representative live data",
                "Register and begin continuous health probes",
            ],
            "safety": "Generated source is constrained to a no-import template and validated before registration.",
        }
