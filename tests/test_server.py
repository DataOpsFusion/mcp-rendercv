"""
Integration tests for the MCP tool handlers.

These call the tool functions directly (not through an MCP transport)
to test argument validation, error handling, and response shapes.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

import rendercv_mcp.server as srv
from rendercv_mcp.executor import CommandResult, WorkspaceViolation


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _ok_result(**kwargs) -> CommandResult:
    return CommandResult(ok=True, stdout="", stderr="", returncode=0, **kwargs)


def _fail_result(stderr: str = "error: bad yaml") -> CommandResult:
    return CommandResult(ok=False, stdout="", stderr=stderr, returncode=1)


# ------------------------------------------------------------------
# rendercv_render
# ------------------------------------------------------------------

class TestRenderTool:
    def test_inline_missing_content(self):
        result = srv.rendercv_render(input_mode="inline", yaml_content=None)
        assert not result["ok"]
        assert "yaml_content" in result["error"]

    def test_path_missing_path(self):
        result = srv.rendercv_render(input_mode="path", yaml_path=None)
        assert not result["ok"]
        assert "yaml_path" in result["error"]

    def test_workspace_violation_surfaces_as_error(self, tmp_path):
        with patch.object(srv.executor, "resolve_yaml_path", side_effect=WorkspaceViolation("outside")):
            result = srv.rendercv_render(input_mode="path", yaml_path="/etc/passwd")
        assert not result["ok"]
        assert "outside" in result["error"]

    def test_successful_render_shape(self, tmp_path):
        fake_artifacts = [{"type": "pdf", "filename": "cv.pdf", "path": "/ws/output/abc/cv.pdf", "size_bytes": 1024}]
        with (
            patch.object(srv.executor, "new_job_id", return_value="abc123"),
            patch.object(srv.executor, "write_inline_yaml", return_value=Path("/ws/input/abc123.yaml")),
            patch.object(srv.executor, "render", return_value=_ok_result(artifacts=fake_artifacts)),
        ):
            result = srv.rendercv_render(input_mode="inline", yaml_content="cv:\n  name: Test\n")

        assert result["ok"]
        assert result["job_id"] == "abc123"
        assert result["artifacts"] == fake_artifacts

    def test_failed_render_shape(self):
        with (
            patch.object(srv.executor, "new_job_id", return_value="fail001"),
            patch.object(srv.executor, "write_inline_yaml", return_value=Path("/ws/input/fail001.yaml")),
            patch.object(srv.executor, "render", return_value=_fail_result("error: invalid field")),
        ):
            result = srv.rendercv_render(input_mode="inline", yaml_content="bad: yaml")

        assert not result["ok"]
        assert "invalid field" in result["stderr"]


# ------------------------------------------------------------------
# rendercv_validate
# ------------------------------------------------------------------

class TestValidateTool:
    def test_inline_missing_content(self):
        result = srv.rendercv_validate(input_mode="inline", yaml_content=None)
        assert not result["ok"]
        assert not result["valid"]

    def test_valid_response_shape(self):
        with (
            patch.object(srv.executor, "new_job_id", return_value="val001"),
            patch.object(srv.executor, "write_inline_yaml", return_value=Path("/ws/input/val001.yaml")),
            patch.object(srv.executor, "validate", return_value=_ok_result()),
        ):
            result = srv.rendercv_validate(input_mode="inline", yaml_content="cv:\n  name: OK\n")

        assert result["ok"]
        assert result["valid"]
        assert isinstance(result["errors"], list)
        assert isinstance(result["warnings"], list)

    def test_error_extraction(self):
        stderr = "error: field 'name' must be a string\nwarning: missing phone\nsome other line"
        with (
            patch.object(srv.executor, "new_job_id", return_value="val002"),
            patch.object(srv.executor, "write_inline_yaml", return_value=Path("/ws/input/val002.yaml")),
            patch.object(srv.executor, "validate", return_value=_fail_result(stderr=stderr)),
        ):
            result = srv.rendercv_validate(input_mode="inline", yaml_content="bad")

        assert not result["valid"]
        assert any("error" in e.lower() for e in result["errors"])
        assert any("warning" in w.lower() for w in result["warnings"])


# ------------------------------------------------------------------
# rendercv_list_themes
# ------------------------------------------------------------------

def test_list_themes_always_succeeds():
    result = srv.rendercv_list_themes()
    assert result["ok"]
    names = [t["name"] for t in result["themes"]]
    assert "classic" in names
    assert "engineeringresumes" in names


# ------------------------------------------------------------------
# rendercv_list_artifacts
# ------------------------------------------------------------------

def test_list_artifacts_empty_for_unknown_job():
    with patch.object(srv.executor, "list_job_artifacts", return_value=[]):
        result = srv.rendercv_list_artifacts("nonexistent")
    assert result["ok"]
    assert result["artifacts"] == []


def test_list_artifacts_returns_metadata():
    fake = [{"type": "pdf", "filename": "cv.pdf", "path": "/x/cv.pdf", "size_bytes": 512}]
    with patch.object(srv.executor, "list_job_artifacts", return_value=fake):
        result = srv.rendercv_list_artifacts("job123")
    assert result["artifacts"] == fake


# ------------------------------------------------------------------
# rendercv_read_artifact
# ------------------------------------------------------------------

def test_read_text_artifact():
    content = "<html><body>Resume</body></html>"
    with patch.object(srv.executor, "read_artifact", return_value=content.encode()):
        result = srv.rendercv_read_artifact("job123", "resume.html")
    assert result["ok"]
    assert result["encoding"] == "utf-8"
    assert result["content"] == content


def test_read_binary_artifact_is_base64():
    with patch.object(srv.executor, "read_artifact", return_value=b"\x89PNG..."):
        result = srv.rendercv_read_artifact("job123", "resume.png")
    assert result["ok"]
    assert result["encoding"] == "base64"


def test_read_artifact_not_found():
    with patch.object(srv.executor, "read_artifact", side_effect=FileNotFoundError("missing")):
        result = srv.rendercv_read_artifact("bad_job", "nope.pdf")
    assert not result["ok"]
    assert "missing" in result["error"]


def test_read_artifact_workspace_violation():
    with patch.object(srv.executor, "read_artifact", side_effect=WorkspaceViolation("invalid filename")):
        result = srv.rendercv_read_artifact("job123", "../resume.html")
    assert not result["ok"]
    assert "invalid filename" in result["error"]
