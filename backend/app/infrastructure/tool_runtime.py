"""Sandboxed loading and execution for validated generated tools."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Awaitable, Callable

from backend.app.core.models import ToolRecord


SAFE_BUILTINS = {
    "bool": bool,
    "dict": dict,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "str": str,
    "ValueError": ValueError,
}


class ToolRuntime:
    def __init__(self, generated_dir: Path):
        self.generated_dir = generated_dir
        self.generated_dir.mkdir(parents=True, exist_ok=True)

    def write(self, filename: str, source: str) -> Path:
        safe_name = Path(filename).name
        if not safe_name.endswith(".py"):
            raise ValueError("Generated tools must be Python modules")
        destination = self.generated_dir / safe_name
        destination.write_text(source, encoding="utf-8")
        return destination

    def load_source(self, filename: str) -> str:
        return (self.generated_dir / Path(filename).name).read_text(encoding="utf-8")

    async def execute_source(
        self,
        source: str,
        payload: dict[str, Any],
        http_get: Callable[[str], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        namespace: dict[str, Any] = {"__builtins__": SAFE_BUILTINS}
        exec(compile(source, "<generated_tool>", "exec"), namespace, namespace)
        execute = namespace.get("execute")
        if execute is None or not inspect.iscoroutinefunction(execute):
            raise TypeError("Generated tool must define async execute(payload, http_get)")
        result = await execute(payload, http_get)
        if not isinstance(result, dict):
            raise TypeError("Generated tool must return an object")
        return result

    async def execute_file(
        self,
        filename: str,
        payload: dict[str, Any],
        http_get: Callable[[str], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        return await self.execute_source(self.load_source(filename), payload, http_get)

    async def execute_registered(
        self,
        tool: ToolRecord,
        payload: dict[str, Any],
        http_get: Callable[[str], Awaitable[dict[str, Any]]],
        execute_operation: Callable[
            [str | None, dict[str, Any]],
            Awaitable[dict[str, Any]],
        ],
    ) -> dict[str, Any]:
        """Execute a registered tool through its actual configured provider."""

        if tool.generated and tool.source_file:
            return await self.execute_file(tool.source_file, payload, http_get)
        return await execute_operation(tool.operation, payload)
