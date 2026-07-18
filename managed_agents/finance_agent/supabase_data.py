"""Constrained, read-only access to the Finance Agent's Supabase tables."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_INVOICE_TABLE = "finance_invoices"
INVOICE_COLUMNS = (
    "invoice_id,customer_name,status,amount,due_date,notes,updated_at"
)


def _credentials() -> tuple[str, str]:
    base_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = (
        os.getenv("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_PUBLISHABLE_KEY")
        or ""
    ).strip()
    if not base_url:
        raise ValueError("SUPABASE_URL is required for database access")
    if not key:
        raise ValueError(
            "SUPABASE_SECRET_KEY or SUPABASE_PUBLISHABLE_KEY is required "
            "for database access"
        )
    return base_url, key


def _invoice_table() -> str:
    table = os.getenv(
        "SUPABASE_FINANCE_TABLE",
        DEFAULT_INVOICE_TABLE,
    ).strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise ValueError("SUPABASE_FINANCE_TABLE is not a valid table name")
    return table


def _matching_count(content_range: str | None) -> int | None:
    if not content_range or "/" not in content_range:
        return None
    total = content_range.rsplit("/", 1)[-1]
    return int(total) if total.isdigit() else None


def _amount_total(rows: list[dict[str, Any]]) -> float:
    total = Decimal("0")
    for row in rows:
        try:
            total += Decimal(str(row.get("amount") or 0))
        except InvalidOperation:
            continue
    return float(total.quantize(Decimal("0.01")))


def query_invoices(
    *,
    status: str | None = None,
    invoice_id: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Read a bounded invoice result set through Supabase PostgREST."""

    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    filters: dict[str, str] = {}
    params: list[tuple[str, str | int]] = [
        ("select", INVOICE_COLUMNS),
        ("limit", limit),
        ("order", "due_date.asc"),
    ]
    if status:
        normalized_status = status.strip().lower()
        if not re.fullmatch(r"[a-z0-9_-]{1,40}", normalized_status):
            raise ValueError("status contains unsupported characters")
        filters["status"] = normalized_status
        params.append(("status", f"eq.{normalized_status}"))
    if invoice_id:
        normalized_invoice = invoice_id.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", normalized_invoice):
            raise ValueError("invoice_id contains unsupported characters")
        filters["invoice_id"] = normalized_invoice
        params.append(("invoice_id", f"eq.{normalized_invoice}"))

    base_url, key = _credentials()
    table = _invoice_table()
    endpoint = (
        f"{base_url}/rest/v1/{table}?"
        f"{urlencode(params)}"
    )
    request = Request(
        endpoint,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "Prefer": "count=exact",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            rows = json.loads(response.read().decode("utf-8"))
            content_range = response.headers.get("Content-Range")
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise PermissionError(
                "Supabase rejected the configured database credentials"
            ) from exc
        raise RuntimeError(
            f"Supabase database returned HTTP {exc.code}"
        ) from exc
    except URLError as exc:
        raise ConnectionError(
            f"Could not reach Supabase database: {exc.reason}"
        ) from exc

    if not isinstance(rows, list) or any(
        not isinstance(row, dict) for row in rows
    ):
        raise RuntimeError("Supabase returned an unexpected invoice payload")

    source = f"supabase://database/{table}"
    statuses = Counter(
        str(row.get("status") or "unknown") for row in rows
    )
    return {
        "data_source": "supabase",
        "source": source,
        "table": table,
        "filters": filters,
        "returned_count": len(rows),
        "total_matching": _matching_count(content_range),
        "status_counts": dict(sorted(statuses.items())),
        "total_amount": _amount_total(rows),
        "rows": rows,
        "evidence": {
            "source": source,
            "table": table,
            "content_range": content_range,
            "columns": INVOICE_COLUMNS.split(","),
            "pulled_live": True,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        },
    }
