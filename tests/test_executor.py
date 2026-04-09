"""
Tests for the RenderCVExecutor subprocess wrapper.

Skips automatically when rendercv is not installed.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from rendercv_mcp.executor import RenderCVExecutor, WorkspaceViolation

STARTER_YAML = """\
cv:
  name: Test Person
  sections:
    education:
      - institution: Test University
        area: Computer Science
        degree: BS
        start_date: 2020-09
        end_date: 2024-05
design:
  theme: classic
"""

BROKEN_YAML = """\
cv:
  name: 12345
  sections:
    education:
      - not_a_valid_field: oops
"""


@pytest.fixture()
def workspace(tmp_path: Path) -> RenderCVExecutor:
    return RenderCVExecutor(tmp_path / "workspace")


@pytest.fixture()
def rendercv_available(workspace: RenderCVExecutor) -> bool:
    ok, _ = workspace.health_check()
    return ok


# ------------------------------------------------------------------
# Workspace safety
# ------------------------------------------------------------------

def test_workspace_violation_absolute(workspace: RenderCVExecutor) -> None:
    with pytest.raises(WorkspaceViolation):
        workspace.resolve_yaml_path("/etc/passwd")


def test_workspace_violation_outside_tmp(workspace: RenderCVExecutor, tmp_path: Path) -> None:
    outside = tmp_path / "outside.yaml"
    outside.write_text("cv:\n  name: Hacker\n")
    with pytest.raises(WorkspaceViolation):
        workspace.resolve_yaml_path(str(outside))


# ------------------------------------------------------------------
# Inline YAML
# ------------------------------------------------------------------

def test_write_inline_yaml(workspace: RenderCVExecutor) -> None:
    job_id = workspace.new_job_id()
    path = workspace.write_inline_yaml(STARTER_YAML, job_id)
    assert path.exists()
    assert path.read_text() == STARTER_YAML
    assert str(path).startswith(str(workspace.workspace_root))


def test_write_inline_yaml_size_limit(workspace: RenderCVExecutor) -> None:
    from rendercv_mcp import config
    oversized = "x" * (config.MAX_YAML_BYTES + 1)
    with pytest.raises(ValueError, match="byte limit"):
        workspace.write_inline_yaml(oversized, workspace.new_job_id())


# ------------------------------------------------------------------
# Render
# ------------------------------------------------------------------

def test_render_valid_yaml(workspace: RenderCVExecutor, rendercv_available: bool) -> None:
    if not rendercv_available:
        pytest.skip("rendercv not installed")

    job_id = workspace.new_job_id()
    yaml_path = workspace.write_inline_yaml(STARTER_YAML, job_id)
    result = workspace.render(yaml_path, job_id=job_id)

    assert result.ok, f"Render failed:\n{result.stderr}"
    assert len(result.artifacts) > 0
    for artifact in result.artifacts:
        assert Path(artifact["path"]).exists()
        assert str(artifact["path"]).startswith(str(workspace.workspace_root))


def test_render_broken_yaml(workspace: RenderCVExecutor, rendercv_available: bool) -> None:
    if not rendercv_available:
        pytest.skip("rendercv not installed")

    job_id = workspace.new_job_id()
    yaml_path = workspace.write_inline_yaml(BROKEN_YAML, job_id)
    result = workspace.render(yaml_path, job_id=job_id)

    assert not result.ok


# ------------------------------------------------------------------
# Validate
# ------------------------------------------------------------------

def test_validate_valid_yaml(workspace: RenderCVExecutor, rendercv_available: bool) -> None:
    if not rendercv_available:
        pytest.skip("rendercv not installed")

    job_id = workspace.new_job_id()
    yaml_path = workspace.write_inline_yaml(STARTER_YAML, job_id)
    result = workspace.validate(yaml_path)

    assert result.ok
    assert result.artifacts == []


def test_validate_leaves_no_artifacts(
    workspace: RenderCVExecutor, rendercv_available: bool
) -> None:
    if not rendercv_available:
        pytest.skip("rendercv not installed")

    job_id = workspace.new_job_id()
    yaml_path = workspace.write_inline_yaml(STARTER_YAML, job_id)
    workspace.validate(yaml_path)

    output_dir = workspace.workspace_root / "output"
    for d in output_dir.iterdir():
        remaining = list(d.iterdir())
        assert remaining == [], f"Unexpected artifacts left in {d}: {remaining}"


# ------------------------------------------------------------------
# new_resume
# ------------------------------------------------------------------

def test_new_resume(workspace: RenderCVExecutor, rendercv_available: bool) -> None:
    if not rendercv_available:
        pytest.skip("rendercv not installed")

    result = workspace.new_resume("Jane Smith", theme="classic")

    assert result.ok, f"new_resume failed:\n{result.stderr}"
    assert len(result.artifacts) == 1
    yaml_path = Path(result.artifacts[0]["path"])
    assert yaml_path.exists()
    assert yaml_path.suffix == ".yaml"


# ------------------------------------------------------------------
# Artifact helpers
# ------------------------------------------------------------------

def test_list_job_artifacts_missing_job(workspace: RenderCVExecutor) -> None:
    result = workspace.list_job_artifacts("nonexistent-job-id")
    assert result == []


def test_list_job_artifacts_rejects_workspace_traversal(
    workspace: RenderCVExecutor,
) -> None:
    with pytest.raises(WorkspaceViolation):
        workspace.list_job_artifacts("../input")


def test_read_artifact_outside_workspace(workspace: RenderCVExecutor) -> None:
    with pytest.raises(WorkspaceViolation):
        workspace.read_artifact("../../etc", "passwd")


def test_read_artifact_rejects_output_subtree_escape(
    workspace: RenderCVExecutor,
) -> None:
    with pytest.raises(WorkspaceViolation):
        workspace.read_artifact("..", "demo.yaml")


# ------------------------------------------------------------------
# Purge old jobs
# ------------------------------------------------------------------

def test_purge_old_jobs(workspace: RenderCVExecutor) -> None:
    from rendercv_mcp import config

    output_dir = workspace.workspace_root / "output"
    # Create more dirs than the keep limit
    keep = 3
    original_keep = config.ARTIFACT_KEEP_JOBS
    config.ARTIFACT_KEEP_JOBS = keep

    for i in range(keep + 2):
        d = output_dir / f"job_{i:03d}"
        d.mkdir()
        (d / "file.pdf").write_bytes(b"fake")

    deleted = workspace.purge_old_jobs()
    remaining = list(output_dir.iterdir())

    config.ARTIFACT_KEEP_JOBS = original_keep  # restore

    assert deleted == 2
    assert len(remaining) == keep
