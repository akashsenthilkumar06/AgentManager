from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from backend.app.core.models import (
    WorkspaceEntry,
    WorkspaceFileContent,
    WorkspaceFileMatch,
    WorkspaceListing,
)
from backend.app.infrastructure.agent_process import AgentProcessManager


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
    """Traversal-safe access to one explicitly configured workspace root."""

    def __init__(self, root: Path, max_preview_bytes: int = 120_000):
        self.root = root.resolve()
        self.max_preview_bytes = max_preview_bytes

    def list_directory(
        self, relative_path: str = "", root: Path | None = None
    ) -> WorkspaceListing:
        workspace_root = self._workspace_root(root)
        directory = self._resolve(relative_path, workspace_root)
        if not directory.is_dir():
            raise NotADirectoryError(relative_path or ".")
        entries: list[WorkspaceEntry] = []
        for child in sorted(directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            if not self._visible(child, workspace_root):
                continue
            stat = child.stat()
            entries.append(WorkspaceEntry(
                path=child.relative_to(workspace_root).as_posix(),
                name=child.name,
                kind="directory" if child.is_dir() else "file",
                size=0 if child.is_dir() else stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                previewable=child.is_file() and child.suffix.lower() in TEXT_SUFFIXES and stat.st_size <= self.max_preview_bytes * 4,
            ))
        relative = directory.relative_to(workspace_root)
        parent = None if directory == workspace_root else (relative.parent.as_posix() if relative.parent.as_posix() != "." else "")
        return WorkspaceListing(root_name=workspace_root.name, path="" if relative.as_posix() == "." else relative.as_posix(), parent=parent, entries=entries)

    def read_file(
        self, relative_path: str, root: Path | None = None
    ) -> WorkspaceFileContent:
        workspace_root = self._workspace_root(root)
        path = self._resolve(relative_path, workspace_root)
        if not path.is_file():
            raise FileNotFoundError(relative_path)
        if not self._visible(path, workspace_root) or path.suffix.lower() not in TEXT_SUFFIXES:
            raise PermissionError("This file type is not available for preview")
        raw = path.read_bytes()
        truncated = len(raw) > self.max_preview_bytes
        content = raw[: self.max_preview_bytes].decode("utf-8", errors="replace")
        return WorkspaceFileContent(
            path=path.relative_to(workspace_root).as_posix(),
            name=path.name,
            language=LANGUAGES.get(path.suffix.lower(), "text"),
            size=len(raw),
            content=content,
            truncated=truncated,
        )

    def write_text_file(
        self,
        relative_path: str,
        content: str,
        root: Path | None = None,
    ) -> dict[str, object]:
        """Write one non-sensitive source/text file inside a managed root."""

        workspace_root = self._workspace_root(root)
        normalized = relative_path.strip().replace("\\", "/")
        if not normalized:
            raise ValueError("A relative file path is required")
        relative = Path(normalized)
        if relative.is_absolute():
            raise PermissionError("File writes require a relative path")
        if any(
            part in {"", ".", ".."} or part.startswith(".")
            for part in relative.parts
        ):
            raise PermissionError(
                "Hidden paths and traversal are not writable"
            )
        path = self._resolve(normalized, workspace_root)
        if path.suffix.lower() not in TEXT_SUFFIXES:
            raise PermissionError(
                "Only supported source and text files are writable"
            )
        if not self._visible(path, workspace_root):
            raise PermissionError("This path is excluded from workspace writes")
        if path.exists() and (path.is_symlink() or not path.is_file()):
            raise PermissionError(
                "Existing symlinks and non-file paths are not writable"
            )
        if not path.parent.is_dir():
            raise FileNotFoundError(
                "The destination directory does not exist"
            )
        encoded = content.encode("utf-8")
        if len(encoded) > self.max_preview_bytes:
            raise ValueError(
                f"File content exceeds the {self.max_preview_bytes}-byte limit"
            )

        previous = path.read_bytes() if path.exists() else None
        temporary = path.with_name(f".{path.name}.agent-manager.tmp")
        temporary.write_bytes(encoded)
        temporary.replace(path)
        return {
            "path": path.relative_to(workspace_root).as_posix(),
            "created": previous is None,
            "bytes": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "previous_sha256": (
                hashlib.sha256(previous).hexdigest()
                if previous is not None
                else None
            ),
            "preview": content[:800],
        }

    async def run_python_file(
        self,
        relative_path: str,
        root: Path | None = None,
        timeout_seconds: float = 10.0,
    ) -> dict[str, object]:
        """Run one scoped Python file without a shell or inherited secrets."""

        workspace_root = self._workspace_root(root)
        path = self._resolve(relative_path.strip(), workspace_root)
        if path.suffix.lower() != ".py":
            raise PermissionError("Only Python source files can be run here")
        if (
            not path.is_file()
            or path.is_symlink()
            or not self._visible(path, workspace_root)
        ):
            raise FileNotFoundError(relative_path)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(path),
            cwd=str(workspace_root),
            env=AgentProcessManager._child_environment(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            raise ValueError(
                f"Python verification exceeded {timeout_seconds:g} seconds"
            ) from None
        output = stdout.decode("utf-8", errors="replace")[:20_000]
        return {
            "path": path.relative_to(workspace_root).as_posix(),
            "command": [sys.executable, path.name],
            "exit_code": process.returncode,
            "stdout": output,
            "passed": process.returncode == 0,
        }

    def search(
        self, query: str, limit: int = 8, root: Path | None = None
    ) -> list[WorkspaceFileMatch]:
        workspace_root = self._workspace_root(root)
        terms = {word for word in re.findall(r"[a-z0-9_]+", query.lower()) if len(word) > 2}
        if not terms:
            return []
        matches: list[WorkspaceFileMatch] = []
        scanned = 0
        for path in workspace_root.rglob("*"):
            if scanned >= 600:
                break
            if not path.is_file() or not self._visible(path, workspace_root) or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            scanned += 1
            relative = path.relative_to(workspace_root).as_posix()
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

    def summary(self, root: Path | None = None) -> dict[str, object]:
        workspace_root = self._workspace_root(root)
        files = directories = 0
        for path in workspace_root.rglob("*"):
            if not self._visible(path, workspace_root):
                continue
            if path.is_dir(): directories += 1
            elif path.is_file(): files += 1
            if files + directories >= 5000: break
        return {"root_name": workspace_root.name, "root_path": str(workspace_root), "files": files, "directories": directories, "read_only": True}

    def validate_root(self, root: Path) -> Path:
        workspace_root = root.expanduser().resolve()
        if not workspace_root.exists():
            raise FileNotFoundError(str(workspace_root))
        if not workspace_root.is_dir():
            raise NotADirectoryError(str(workspace_root))
        return workspace_root

    def inspect_agent_project(
        self,
        root: Path,
    ) -> dict[str, object]:
        """Detect a local agent project's shape without reading secrets."""

        workspace_root = self.validate_root(root)
        summary = self.summary(workspace_root)
        commands: list[str] = []
        languages: set[str] = set()
        indexed_files = 0
        for path in workspace_root.rglob("*"):
            if indexed_files >= 1000:
                break
            if not path.is_file() or not self._visible(
                path,
                workspace_root,
            ) or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            indexed_files += 1
            language = LANGUAGES.get(path.suffix.lower())
            if language:
                languages.add(language)

        package_path = workspace_root / "package.json"
        if package_path.is_file() and self._visible(
            package_path,
            workspace_root,
        ):
            try:
                package = json.loads(
                    package_path.read_text(encoding="utf-8")
                )
                scripts = package.get("scripts", {})
                package_manager = (
                    "pnpm"
                    if (workspace_root / "pnpm-lock.yaml").exists()
                    else (
                        "yarn"
                        if (workspace_root / "yarn.lock").exists()
                        else "npm"
                    )
                )
                for script in ("dev", "start", "serve"):
                    if script not in scripts:
                        continue
                    if package_manager == "yarn":
                        commands.append(f"yarn {script}")
                    else:
                        commands.append(
                            f"{package_manager} run {script}"
                        )
            except (ValueError, OSError):
                pass

        makefile = workspace_root / "Makefile"
        if makefile.is_file():
            make_text = makefile.read_text(
                encoding="utf-8",
                errors="ignore",
            )
            for target in ("dev", "run", "start"):
                if re.search(
                    rf"(?m)^{re.escape(target)}\s*:",
                    make_text,
                ):
                    commands.append(f"make {target}")

        pyproject = workspace_root / "pyproject.toml"
        if pyproject.is_file():
            try:
                parsed = tomllib.loads(
                    pyproject.read_text(encoding="utf-8")
                )
                scripts = parsed.get("project", {}).get("scripts", {})
                for target in list(scripts)[:3]:
                    commands.append(target)
            except (ValueError, OSError):
                pass
        for filename in ("main.py", "app.py", "server.py"):
            if (workspace_root / filename).is_file():
                commands.append(f"python {filename}")

        readme = next(
            (
                path
                for path in (
                    workspace_root / "README.md",
                    workspace_root / "README.txt",
                    workspace_root / "readme.md",
                )
                if path.is_file()
            ),
            None,
        )
        description = ""
        if readme:
            content = readme.read_text(
                encoding="utf-8",
                errors="ignore",
            )[:8000]
            paragraphs = [
                re.sub(r"[#*_`>\[\]]", "", paragraph).strip()
                for paragraph in re.split(r"\n\s*\n", content)
                if paragraph.strip()
            ]
            description = next(
                (
                    paragraph.replace("\n", " ")
                    for paragraph in paragraphs
                    if len(paragraph) >= 20
                ),
                "",
            )[:500]

        instructions = ""
        for filename in (
            "AGENTS.md",
            "SYSTEM_PROMPT.md",
            "system_prompt.txt",
            "instructions.md",
        ):
            path = workspace_root / filename
            if path.is_file() and self._visible(path, workspace_root):
                instructions = path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )[:4000].strip()
                if instructions:
                    break

        detected_endpoint = None
        for filename in ("agent.json", "mcp.json"):
            path = workspace_root / filename
            if not path.is_file():
                continue
            try:
                configuration = json.loads(
                    path.read_text(encoding="utf-8")
                )
            except (ValueError, OSError):
                continue
            candidate = configuration.get(
                "mcp_endpoint",
                configuration.get("endpoint"),
            )
            if isinstance(candidate, str) and candidate.startswith(
                ("demo://", "http://", "https://")
            ):
                detected_endpoint = candidate
                break

        return {
            **summary,
            "indexed_files": indexed_files,
            "languages": sorted(languages),
            "detected_entrypoints": list(dict.fromkeys(commands))[:8],
            "description": description,
            "instructions": instructions,
            "mcp_endpoint": detected_endpoint,
        }

    def _workspace_root(self, root: Path | None) -> Path:
        return self.validate_root(root or self.root)

    def _resolve(self, relative_path: str, root: Path) -> Path:
        candidate = (root / relative_path).resolve()
        if candidate != root and root not in candidate.parents:
            raise PermissionError("Path escapes the configured workspace root")
        if any(part in EXCLUDED_DIRECTORIES for part in candidate.relative_to(root).parts):
            raise PermissionError("Path is excluded from workspace access")
        return candidate

    def _visible(self, path: Path, root: Path) -> bool:
        try:
            relative_parts = path.relative_to(root).parts
            resolved = path.resolve()
            if resolved != root and root not in resolved.parents:
                return False
            resolved_parts = resolved.relative_to(root).parts
        except ValueError:
            return False
        return (
            not any(part in EXCLUDED_DIRECTORIES for part in relative_parts)
            and not any(
                part in EXCLUDED_DIRECTORIES
                for part in resolved_parts
            )
            and path.name not in SENSITIVE_NAMES
            and resolved.name not in SENSITIVE_NAMES
            and path.suffix.lower() not in SENSITIVE_SUFFIXES
            and resolved.suffix.lower() not in SENSITIVE_SUFFIXES
            and not path.name.startswith(".env")
            and not resolved.name.startswith(".env")
        )
