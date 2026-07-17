from __future__ import annotations

import ast
import time
from typing import Any

from backend.app.core.models import ToolRecord, ValidationCheck
from backend.app.infrastructure.mock_system import MockSystem
from backend.app.infrastructure.tool_runtime import ToolRuntime


FORBIDDEN_NODES = (ast.Import, ast.ImportFrom, ast.ClassDef, ast.Global, ast.Nonlocal, ast.Lambda)
FORBIDDEN_CALLS = {"eval", "exec", "open", "compile", "__import__", "getattr", "setattr", "delattr"}


class ValidationAgent:
    def __init__(self, runtime: ToolRuntime, mock_system: MockSystem):
        self.runtime = runtime
        self.mock_system = mock_system

    async def validate(self, source: str, tool: ToolRecord, available_endpoints: set[str]) -> list[ValidationCheck]:
        checks: list[ValidationCheck] = []

        started = time.perf_counter()
        try:
            tree = ast.parse(source)
            forbidden = [node.__class__.__name__ for node in ast.walk(tree) if isinstance(node, FORBIDDEN_NODES)]
            dangerous = [
                node.func.id
                for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS
            ]
            if forbidden or dangerous:
                raise ValueError("Forbidden syntax: " + ", ".join(forbidden + dangerous))
            functions = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "execute"]
            if len(functions) != 1 or len(functions[0].args.args) != 2:
                raise ValueError("Expected async execute(payload, http_get)")
            checks.append(self._check("Static safety", "passed", "AST is valid and contains no imports or unsafe calls.", started))
        except Exception as exc:
            checks.append(self._check("Static safety", "failed", str(exc), started))
            return checks

        started = time.perf_counter()
        missing = set(tool.endpoint_ids) - available_endpoints
        checks.append(
            self._check(
                "Dependency resolution",
                "failed" if missing else "passed",
                f"Missing endpoints: {', '.join(sorted(missing))}" if missing else f"Resolved {len(tool.endpoint_ids)} existing endpoint(s).",
                started,
            )
        )

        started = time.perf_counter()
        schema_error = self._schema_error(tool.input_schema) or self._schema_error(tool.output_schema)
        checks.append(
            self._check(
                "Schema contract",
                "failed" if schema_error else "passed",
                schema_error or "Input and output contracts are structurally valid.",
                started,
            )
        )

        started = time.perf_counter()
        try:
            result = await self.runtime.execute_source(source, tool.probe_input, self.mock_system.get)
            checks.append(self._check("Representative execution", "passed", "Tool completed against live demo endpoints.", started))
        except Exception as exc:
            result = {}
            checks.append(self._check("Representative execution", "failed", str(exc), started))

        started = time.perf_counter()
        required = set(tool.output_schema.get("required", []))
        absent = required - set(result)
        checks.append(
            self._check(
                "Output verification",
                "failed" if absent else "passed",
                f"Missing output fields: {', '.join(sorted(absent))}" if absent else f"Verified {len(required)} required output fields.",
                started,
            )
        )
        return checks

    @staticmethod
    def _schema_error(schema: dict[str, Any]) -> str | None:
        if schema.get("type") != "object":
            return "Top-level schema type must be object."
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return "Schema properties must be an object."
        if not set(schema.get("required", [])).issubset(properties):
            return "Every required field must be declared in properties."
        return None

    @staticmethod
    def _check(name: str, status: str, detail: str, started: float) -> ValidationCheck:
        return ValidationCheck(
            name=name,
            status=status,  # type: ignore[arg-type]
            detail=detail,
            duration_ms=max(1, round((time.perf_counter() - started) * 1000)),
        )
