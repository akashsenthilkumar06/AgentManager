from __future__ import annotations

import re
from typing import Any

from backend.app.infrastructure.mock_system import MockSystem


AGENT_ID = "coding-agent"
REQUIRED_TOOL = ("review-code", "review_code")


async def run(mock_system: MockSystem, message: str) -> dict[str, Any]:
    repo_id = _identifier(message.upper(), r"REPO-\d+", "REPO-1")
    output = await mock_system.get(f"/mock/codebase/{repo_id}")
    content = (
        f"{repo_id} is {output['status'].replace('_', ' ')}. "
        f"Coverage is {output['coverage']}% with {output['failing_tests']} failing tests and {output['open_issues']} open issues."
    )
    return {
        "tool_id": REQUIRED_TOOL[0],
        "tool_name": REQUIRED_TOOL[1],
        "inputs": {"repo_id": repo_id},
        "output": output,
        "content": content,
        "criteria": [
            "Identify the requested repository",
            "Report release health and test coverage",
            "Call out any release risk signals",
        ],
        "evidence": [
            f"Codebase API returned status={output['status']}",
            f"Matched repo_id={repo_id}; source={output['_data_source']}",
        ],
    }


def _identifier(message: str, pattern: str, fallback: str) -> str:
    match = re.search(pattern, message)
    return match.group(0) if match else fallback
