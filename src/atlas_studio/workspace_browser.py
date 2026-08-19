"""Secure read-only browsing for the explicitly configured developer workspace."""

from pathlib import Path, PurePosixPath


EXCLUDED_NAMES = {
    ".git", ".hg", ".svn", ".idea", ".vscode", ".venv", "venv",
    "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "dist", "build", "coverage", ".coverage", "models",
    "outputs", "runtime", "work",
}
SENSITIVE_NAMES = {
    ".env", ".npmrc", ".pypirc", "id_rsa", "id_ed25519",
    "credentials", "credentials.json", "secrets.json",
}
SENSITIVE_PARTS = ("secret", "token", "password", "credential", "private_key")
TEXT_EXTENSIONS = {
    ".css", ".csv", ".dockerignore", ".env.example", ".gitignore", ".graphql",
    ".html", ".ini", ".java", ".js", ".json", ".jsx", ".md", ".mjs",
    ".py", ".pyi", ".ps1", ".rb", ".rs", ".sh", ".sql", ".toml", ".ts",
    ".tsx", ".txt", ".xml", ".yaml", ".yml",
}
TEXT_NAMES = {"dockerfile", "makefile", "license"}
LANGUAGE_BY_SUFFIX = {
    ".css": "css", ".html": "html", ".js": "javascript", ".jsx": "javascript",
    ".json": "json", ".md": "markdown", ".mjs": "javascript", ".py": "python",
    ".ps1": "powershell", ".sh": "shell", ".sql": "sql", ".toml": "toml",
    ".ts": "typescript", ".tsx": "typescript", ".xml": "xml", ".yaml": "yaml",
    ".yml": "yaml",
}


class WorkspacePathError(ValueError):
    pass


class WorkspaceBrowser:
    def __init__(self, root: Path, max_preview_kb: int = 512):
        self.root = root.resolve()
        self.max_preview_bytes = max_preview_kb * 1024

    def _relative(self, raw_path: str) -> PurePosixPath:
        if "\\" in raw_path:
            raise WorkspacePathError("workspace paths must use forward slashes")
        relative = PurePosixPath(raw_path or ".")
        if relative.is_absolute() or ".." in relative.parts:
            raise WorkspacePathError("path traversal rejected")
        if any(self._excluded(part) for part in relative.parts if part not in ("", ".")):
            raise WorkspacePathError("path is excluded from the workspace explorer")
        return relative

    @staticmethod
    def _excluded(name: str) -> bool:
        folded = name.casefold()
        if folded in EXCLUDED_NAMES or folded in SENSITIVE_NAMES:
            return True
        normalized_parts = folded.replace("-", "_").replace(".", "_").split("_")
        return any(part in normalized_parts for part in SENSITIVE_PARTS)

    def resolve(self, raw_path: str) -> Path:
        if not self.root.is_dir():
            raise WorkspacePathError("configured workspace root is unavailable")
        relative = self._relative(raw_path)
        candidate = (self.root / Path(*relative.parts)).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise WorkspacePathError("path escapes the configured workspace")
        return candidate

    def list_directory(self, raw_path: str = "") -> dict:
        directory = self.resolve(raw_path)
        if not directory.is_dir():
            raise FileNotFoundError("workspace directory not found")
        entries = []
        for item in directory.iterdir():
            if self._excluded(item.name):
                continue
            try:
                resolved = item.resolve()
                if resolved != self.root and self.root not in resolved.parents:
                    continue
                is_directory = item.is_dir()
                if not is_directory and not item.is_file():
                    continue
            except OSError:
                continue
            relative = item.relative_to(self.root).as_posix()
            entries.append(
                {
                    "name": item.name,
                    "path": relative,
                    "type": "directory" if is_directory else "file",
                    "previewable": False if is_directory else self.is_previewable(item),
                }
            )
        entries.sort(key=lambda entry: (entry["type"] != "directory", entry["name"].casefold()))
        return {
            "root": self.root.name,
            "path": "" if directory == self.root else directory.relative_to(self.root).as_posix(),
            "entries": entries[:500],
            "truncated": len(entries) > 500,
            "read_only": True,
        }

    def is_previewable(self, path: Path) -> bool:
        folded = path.name.casefold()
        suffix = path.suffix.casefold()
        compound = ".env.example" if folded.endswith(".env.example") else suffix
        return (folded in TEXT_NAMES or compound in TEXT_EXTENSIONS) and path.stat().st_size <= self.max_preview_bytes

    def read_file(self, raw_path: str) -> dict:
        path = self.resolve(raw_path)
        if not path.is_file():
            raise FileNotFoundError("workspace file not found")
        if not self.is_previewable(path):
            raise WorkspacePathError("file is binary, sensitive, or exceeds the preview limit")
        data = path.read_bytes()
        if b"\x00" in data:
            raise WorkspacePathError("binary files cannot be previewed")
        content = data.decode("utf-8", errors="replace")
        suffix = path.suffix.casefold()
        return {
            "name": path.name,
            "path": path.relative_to(self.root).as_posix(),
            "language": LANGUAGE_BY_SUFFIX.get(suffix, "text"),
            "content": content,
            "size": len(data),
            "line_count": content.count("\n") + (1 if content else 0),
            "read_only": True,
        }
