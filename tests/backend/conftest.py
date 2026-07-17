from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import backend.app.dependencies as dependencies
import backend.app.main as manager


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(dependencies.store, "path", tmp_path / "data" / "state.json")
    monkeypatch.setattr(dependencies.runtime, "generated_dir", tmp_path / "generated_tools")
    dependencies.runtime.generated_dir.mkdir(parents=True, exist_ok=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "orders.py").write_text("def lookup_order(order_id):\n    return order_id\n", encoding="utf-8")
    (workspace / "README.md").write_text("Order and shipment support workspace.", encoding="utf-8")
    (workspace / ".env").write_text("SECRET=not-visible", encoding="utf-8")
    monkeypatch.setattr(dependencies.workspace_access, "root", workspace.resolve())
    with TestClient(manager.app) as test_client:
        yield test_client
