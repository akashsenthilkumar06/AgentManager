from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from backend.app.core.models import (
    WorkspaceEntry,
    WorkspaceFileContent,
    WorkspaceFileMatch,
    WorkspaceListing,
)


EXCLUDED_DIRECTORIES = {".git", ".venv", "node_modules", "dist", "build", "__pycache__", ".pytest_cache", ".idea", ".vscode"}
SENSITIVE_NAMES = {".env", ".env.local", ".env.production", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
TEXT_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".md", ".txt", ".toml", ".yaml", ".yml",
    ".css", ".scss", ".html", ".xml", ".sql", ".sh", ".java", ".go", ".rs", ".c", ".cpp", ".h",
}
LANGUAGES = {
    ".py": "python", ".js": "javascript", ".jsx": "jsx", ".ts": "typescript", ".tsx": "tsx",
    ".json": "json", ".md": "markdown", ".css": "css", ".html": "html", ".toml": "toml",
    ".yaml": "yaml", ".yml": "yaml", ".sql": "sql", ".sh": "shell",
}


class WorkspaceAccess:
    """Read-only, traversal-safe access to one explicitly configured root."""

    def __init__(self, root: Path, max_preview_bytes: int = 120_000):
        self.root = root.resolve()
        self.max_preview_bytes = max_preview_bytes

    def list_directory(self, relative_path: str = "") -> WorkspaceListing:
        directory = self._resolve(relative_path)
        if not directory.is_dir():
            raise NotADirectoryError(relative_path or ".")
        entries: list[WorkspaceEntry] = []
        for child in sorted(directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            if not self._visible(child):
                continue
            stat = child.stat()
            entries.append(WorkspaceEntry(
                path=child.relative_to(self.root).as_posix(),
                name=child.name,
                kind="directory" if child.is_dir() else "file",
                size=0 if child.is_dir() else stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                previewable=child.is_file() and child.suffix.lower() in TEXT_SUFFIXES and stat.st_size <= self.max_preview_bytes * 4,
            ))
        relative = directory.relative_to(self.root)
        parent = None if directory == self.root else (relative.parent.as_posix() if relative.parent.as_posix() != "." else "")
        return WorkspaceListing(root_name=self.root.name, path="" if relative.as_posix() == "." else relative.as_posix(), parent=parent, entries=entries)

    def read_file(self, relative_path: str) -> WorkspaceFileContent:
        path = self._resolve(relative_path)
        if not path.is_file():
            raise FileNotFoundError(relative_path)
        if not self._visible(path) or path.suffix.lower() not in TEXT_SUFFIXES:
            raise PermissionError("This file type is not available for preview")
        raw = path.read_bytes()
        truncated = len(raw) > self.max_preview_bytes
        content = raw[: self.max_preview_bytes].decode("utf-8", errors="replace")
        return WorkspaceFileContent(
            path=path.relative_to(self.root).as_posix(),
            name=path.name,
            language=LANGUAGES.get(path.suffix.lower(), "text"),
            size=len(raw),
            content=content,
            truncated=truncated,
        )

    def search(self, query: str, limit: int = 8) -> list[WorkspaceFileMatch]:
        terms = {word for word in re.findall(r"[a-z0-9_]+", query.lower()) if len(word) > 2}
        if not terms:
            return []
        matches: list[WorkspaceFileMatch] = []
        scanned = 0
        for path in self.root.rglob("*"):
            if scanned >= 600:
                break
            if not path.is_file() or not self._visible(path) or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            scanned += 1
            relative = path.relative_to(self.root).as_posix()
            name_matches = terms.intersection(set(re.findall(r"[a-z0-9_]+", relative.lower())))
            content_matches: set[str] = set()
            if path.stat().st_size <= 80_000:
                content = path.read_text(encoding="utf-8", errors="ignore")[:20_000].lower()
                content_matches = {term for term in terms if term in content}
            overlap = name_matches | content_matches
            if overlap:
                score = min(.99, .25 + len(name_matches) * .25 + len(content_matches) * .08)
                matches.append(WorkspaceFileMatch(
                    path=relative,
                    name=path.name,
                    reason=f"Matched {', '.join(sorted(overlap)[:4])}",
                    score=round(score, 2),
                ))
        matches.sort(key=lambda match: match.score, reverse=True)
        return matches[:limit]

    def summary(self) -> dict[str, object]:
        files = directories = 0
        for path in self.root.rglob("*"):
            if not self._visible(path):
                continue
            if path.is_dir(): directories += 1
            elif path.is_file(): files += 1
            if files + directories >= 5000: break
        return {"root_name": self.root.name, "root_path": str(self.root), "files": files, "directories": directories, "read_only": True}

    def _resolve(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise PermissionError("Path escapes the configured workspace root")
        if any(part in EXCLUDED_DIRECTORIES for part in candidate.relative_to(self.root).parts):
            raise PermissionError("Path is excluded from workspace access")
        return candidate

    def _visible(self, path: Path) -> bool:
        try:
            relative_parts = path.relative_to(self.root).parts
        except ValueError:
            return False
        return (
            not any(part in EXCLUDED_DIRECTORIES for part in relative_parts)
            and path.name not in SENSITIVE_NAMES
            and path.suffix.lower() not in SENSITIVE_SUFFIXES
            and not path.name.startswith(".env")
        )

