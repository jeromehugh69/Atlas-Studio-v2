from pathlib import Path

import pytest

from atlas_studio.workspace_browser import WorkspaceBrowser, WorkspacePathError


def test_workspace_tree_is_read_only_and_hides_sensitive_paths(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('atlas')\n", encoding="utf-8")
    (tmp_path / ".env").write_text("PASSWORD=hidden\n", encoding="utf-8")
    (tmp_path / "service_token.txt").write_text("hidden\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()

    result = WorkspaceBrowser(tmp_path).list_directory()

    assert result["read_only"] is True
    assert [entry["name"] for entry in result["entries"]] == ["src"]
    assert result["entries"][0]["type"] == "directory"


def test_workspace_file_preview_returns_text_and_language(tmp_path: Path):
    source = tmp_path / "atlas.py"
    source.write_text("def ready():\n    return True\n", encoding="utf-8")

    result = WorkspaceBrowser(tmp_path).read_file("atlas.py")

    assert result["language"] == "python"
    assert result["line_count"] == 3
    assert result["content"].startswith("def ready")
    assert result["read_only"] is True


@pytest.mark.parametrize("path", ["../outside.py", "/etc/passwd", ".env", "folder\\file.py"])
def test_workspace_browser_rejects_unsafe_paths(tmp_path: Path, path: str):
    with pytest.raises(WorkspacePathError):
        WorkspaceBrowser(tmp_path).resolve(path)


def test_workspace_browser_rejects_binary_and_large_files(tmp_path: Path):
    (tmp_path / "binary.txt").write_bytes(b"atlas\x00data")
    (tmp_path / "large.txt").write_bytes(b"x" * 2048)
    browser = WorkspaceBrowser(tmp_path, max_preview_kb=1)

    with pytest.raises(WorkspacePathError):
        browser.read_file("binary.txt")
    with pytest.raises(WorkspacePathError):
        browser.read_file("large.txt")
