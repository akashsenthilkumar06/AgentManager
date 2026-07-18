from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

CODEBASE = {
    "REPO-1": {
        "repo_id": "REPO-1",
        "branch": "main",
        "status": "needs_review",
        "coverage": 86.4,
        "failing_tests": 2,
        "open_issues": 5,
        "risk": "medium",
        "summary": "Recent changes touched shared utilities and test coverage slipped below the release threshold.",
    }
}


def match(path: str) -> dict[str, Any] | None:
    matched = re.match(r"^/mock/codebase/([^/]+)$", path)
    if not matched:
        return None
    repo_id = matched.group(1).upper()
    if repo_id not in CODEBASE:
        raise LookupError(f"No record found for {repo_id}")
    return deepcopy(CODEBASE[repo_id])
