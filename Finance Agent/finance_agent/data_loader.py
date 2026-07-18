"""File ingestion and statement classification for common financial-data formats."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import re
import os
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, quote
from urllib.request import Request, urlopen
try:
    import duckdb
except ImportError:  # Useful for source inspection before dependencies are installed.
    duckdb = None
import pandas as pd

from .state import DATA_ROOT

ALIASES = {"revenue": "revenue", "total_revenue": "revenue", "sales": "revenue", "net_sales": "revenue",
 "cost_of_revenue": "cost_of_revenue", "cogs": "cost_of_revenue", "gross_profit": "gross_profit",
 "operating_income": "operating_income", "ebit": "operating_income", "net_income": "net_income",
 "eps": "eps", "earnings_per_share": "eps", "total_assets": "total_assets",
 "total_liabilities": "total_liabilities", "total_equity": "total_equity", "shareholders_equity": "total_equity",
 "current_assets": "current_assets", "current_liabilities": "current_liabilities", "cash": "cash",
 "inventory": "inventory", "total_debt": "total_debt", "operating_cash_flow": "operating_cash_flow",
 "capex": "capex", "capital_expenditures": "capex", "shares_outstanding": "shares_outstanding",
 "price": "price", "close": "price", "date": "date", "year": "year", "period": "year"}


@dataclass
class FinancialData:
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    source: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def latest(self, column: str) -> float | None:
        for frame in self.frames.values():
            if column in frame.columns:
                values = pd.to_numeric(frame[column], errors="coerce").dropna()
                if not values.empty:
                    return float(values.iloc[-1])
        return None

    def series(self, column: str) -> list[float]:
        for frame in self.frames.values():
            if column in frame.columns:
                return pd.to_numeric(frame[column], errors="coerce").dropna().astype(float).tolist()
        return []


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result.columns = [ALIASES.get(re.sub(r"[^a-z0-9]+", "_", str(c).lower()).strip("_"),
                                   re.sub(r"[^a-z0-9]+", "_", str(c).lower()).strip("_")) for c in result.columns]
    for col in result.columns:
        if col not in {"date", "year", "ticker"}:
            converted = pd.to_numeric(result[col].astype(str).str.replace(",", "").str.replace("$", ""), errors="coerce")
            if converted.notna().any():
                result[col] = converted
    if "year" in result.columns:
        result = result.sort_values("year")
    elif "date" in result.columns:
        result = result.sort_values("date")
    return result


def _kind(path: Path, frame: pd.DataFrame) -> str:
    name = path.stem.lower()
    cols = set(frame.columns)
    if "income" in name or "revenue" in cols or "net_income" in cols: return "income_statement"
    if "balance" in name or "total_assets" in cols: return "balance_sheet"
    if "cash" in name or "operating_cash_flow" in cols: return "cash_flow"
    if "stock" in name or "price" in cols: return "stock_history"
    if "ratio" in name: return "ratios"
    if "earning" in name: return "earnings"
    return path.stem


def _read(path: Path) -> dict[str, pd.DataFrame]:
    if path.is_dir():
        output: dict[str, pd.DataFrame] = {}
        for child in sorted(path.iterdir()):
            if child.suffix.lower() in {".csv", ".json", ".xlsx", ".xls", ".parquet"}:
                output.update(_read(child))
        return output
    suffix = path.suffix.lower()
    if suffix == ".csv":
        # DuckDB offers a reproducible CSV parser and is part of this service's local runtime.
        raw = (duckdb.sql("SELECT * FROM read_csv_auto(?)", params=[str(path)]).df()
               if duckdb is not None else pd.read_csv(path))
        frames = {path.stem: raw}
    elif suffix == ".json": frames = {path.stem: pd.read_json(path)}
    elif suffix in {".xlsx", ".xls"}: frames = pd.read_excel(path, sheet_name=None)
    elif suffix == ".parquet": frames = {path.stem: pd.read_parquet(path)}
    else: raise ValueError(f"Unsupported dataset format: {suffix}")
    return {_kind(path, _normalize(df)): _normalize(df) for _, df in frames.items()}


def _read_supabase_storage(uri: str) -> dict[str, pd.DataFrame]:
    """Read one CSV/JSON/Parquet/XLSX object from a Supabase Storage bucket.

    URI format: supabase://<bucket>/<object-path>.csv
    SUPABASE_URL is required. A private bucket additionally requires
    SUPABASE_SECRET_KEY (or legacy SUPABASE_SERVICE_ROLE_KEY).
    """
    parsed = urlparse(uri)
    bucket, object_path = parsed.netloc, parsed.path.lstrip("/")
    if not bucket or not object_path:
        raise ValueError("Supabase dataset_path must be supabase://<bucket>/<object-path>")
    base_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    if not base_url:
        raise ValueError("SUPABASE_URL is required for a supabase:// dataset path")
    key = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    headers = {"apikey": key, "Authorization": f"Bearer {key}"} if key else {}
    endpoint = f"{base_url}/storage/v1/object/{quote(bucket, safe='')}/{quote(object_path, safe='/')}"
    try:
        with urlopen(Request(endpoint, headers=headers), timeout=30) as response:
            content = response.read()
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise PermissionError("Supabase object is private or the Supabase key is invalid") from exc
        raise RuntimeError(f"Supabase Storage returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise ConnectionError(f"Could not reach Supabase Storage: {exc.reason}") from exc
    virtual_path = Path(object_path)
    suffix = virtual_path.suffix.lower()
    stream = BytesIO(content)
    if suffix == ".csv": raw = pd.read_csv(stream)
    elif suffix == ".json": raw = pd.read_json(stream)
    elif suffix in {".xlsx", ".xls"}:
        sheets = pd.read_excel(stream, sheet_name=None)
        return {_kind(virtual_path, _normalize(df)): _normalize(df) for df in sheets.values()}
    elif suffix == ".parquet": raw = pd.read_parquet(stream)
    else: raise ValueError(f"Unsupported Supabase object format: {suffix}")
    normalized = _normalize(raw)
    return {_kind(virtual_path, normalized): normalized}


def load_data(dataset_path: str | None, ticker: str | None = None) -> FinancialData:
    if dataset_path and dataset_path.startswith("supabase://"):
        frames = _read_supabase_storage(dataset_path)
        evidence = [{"source": dataset_path, "statement": name, "rows": len(df), "columns": list(df.columns)} for name, df in frames.items()]
        return FinancialData(frames=frames, source=dataset_path, evidence=evidence)
    path = Path(dataset_path) if dataset_path else DATA_ROOT / ((ticker or "apple").lower())
    if not path.exists():
        raise FileNotFoundError(f"Dataset path does not exist: {path}")
    frames = _read(path)
    evidence = [{"source": str(path), "statement": name, "rows": len(df), "columns": list(df.columns)} for name, df in frames.items()]
    return FinancialData(frames=frames, source=str(path), evidence=evidence)
