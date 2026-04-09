"""
Thin subprocess wrapper around the rendercv CLI.

All paths are validated against the configured workspace root.
Commands are always executed as argument lists — never via shell=True —
to prevent injection through user-supplied content or filenames.
"""

from __future__ import annotations

import secrets
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

from . import config


@dataclass
class CommandResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int
    artifacts: list[dict] = field(default_factory=list)


class WorkspaceViolation(Exception):
    pass


class RenderCVExecutor:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self._semaphore = threading.Semaphore(config.MAX_CONCURRENT_RENDERS)

        for sub in ("input", "output", "themes"):
            (self.workspace_root / sub).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Path safety
    # ------------------------------------------------------------------

    def _safe(self, path: Path) -> Path:
        """Resolve and assert path is inside workspace root."""
        resolved = path.resolve()
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError:
            raise WorkspaceViolation(
                f"{path} is outside workspace root {self.workspace_root}"
            )
        return resolved

    def _safe_name(self, value: str, field: str) -> str:
        """Validate a single path component used within the workspace."""
        if not value or value in {".", ".."}:
            raise WorkspaceViolation(f"Invalid {field}: {value!r}")

        path = Path(value)
        if path.name != value or len(path.parts) != 1:
            raise WorkspaceViolation(f"Invalid {field}: {value!r}")

        return value

    def _job_output_dir(self, job_id: str) -> Path:
        safe_job_id = self._safe_name(job_id, "job_id")
        return self._safe(self.workspace_root / "output" / safe_job_id)

    # ------------------------------------------------------------------
    # Low-level runner
    # ------------------------------------------------------------------

    def _run(
        self,
        args: list[str],
        cwd: Path | None = None,
        timeout: int | None = None,
    ) -> CommandResult:
        cmd = ["rendercv"] + args
        timeout = timeout or config.RENDER_TIMEOUT_SECONDS
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(cwd or self.workspace_root),
            )
            return CommandResult(
                ok=proc.returncode == 0,
                stdout=proc.stdout,
                stderr=proc.stderr,
                returncode=proc.returncode,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                ok=False, stdout="", stderr="Render timed out", returncode=-1
            )
        except FileNotFoundError:
            return CommandResult(
                ok=False,
                stdout="",
                stderr="rendercv not found in PATH — is it installed?",
                returncode=-1,
            )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def health_check(self) -> tuple[bool, str]:
        result = self._run(["--version"], timeout=10)
        if result.ok:
            return True, result.stdout.strip() or result.stderr.strip()
        return False, result.stderr.strip()

    def new_job_id(self) -> str:
        # 16 hex bytes = 128 bits — prevents job enumeration attacks
        return secrets.token_hex(16)

    def write_inline_yaml(self, yaml_content: str, job_id: str) -> Path:
        if len(yaml_content.encode()) > config.MAX_YAML_BYTES:
            raise ValueError(
                f"YAML content exceeds {config.MAX_YAML_BYTES} byte limit"
            )
        dest = self.workspace_root / "input" / f"{job_id}.yaml"
        dest.write_text(yaml_content, encoding="utf-8")
        return self._safe(dest)

    def resolve_yaml_path(self, yaml_path: str) -> Path:
        return self._safe(Path(yaml_path))

    def list_job_artifacts(self, job_id: str) -> list[dict]:
        """Return artifact metadata for a previously rendered job."""
        job_dir = self._job_output_dir(job_id)
        if not job_dir.exists():
            return []
        return [
            {
                "type": f.suffix.lstrip("."),
                "filename": f.name,
                "path": str(f),
                "size_bytes": f.stat().st_size,
            }
            for f in sorted(job_dir.iterdir())
            if f.is_file()
        ]

    def read_artifact(self, job_id: str, filename: str) -> bytes:
        """Read a single artifact file, enforcing workspace safety."""
        safe_filename = self._safe_name(filename, "filename")
        path = self._job_output_dir(job_id) / safe_filename
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {job_id}/{filename}")
        return path.read_bytes()

    def purge_old_jobs(self) -> int:
        """Delete oldest job output directories beyond ARTIFACT_KEEP_JOBS. Returns count deleted."""
        if config.ARTIFACT_KEEP_JOBS == 0:
            return 0
        output_dir = self.workspace_root / "output"
        dirs = sorted(
            (d for d in output_dir.iterdir() if d.is_dir()),
            key=lambda d: d.stat().st_mtime,
        )
        to_delete = dirs[: max(0, len(dirs) - config.ARTIFACT_KEEP_JOBS)]
        for d in to_delete:
            shutil.rmtree(d, ignore_errors=True)
        return len(to_delete)

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def render(
        self,
        yaml_path: Path,
        job_id: str,
        formats: list[str] | None = None,
    ) -> CommandResult:
        """
        Run `rendercv render <yaml_path>` and collect output artifacts.

        RenderCV writes output into a folder named after --output-folder-name
        inside the input file's parent directory.  We name that folder with
        the job_id, then move the results into workspace/output/<job_id>/.
        """
        output_dir = self.workspace_root / "output" / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        args = ["render", str(yaml_path), "--output-folder", str(output_dir)]

        if formats:
            requested = {fmt.lower() for fmt in formats}
            disable_flags = {
                "pdf": "--dont-generate-pdf",
                "html": "--dont-generate-html",
                "markdown": "--dont-generate-markdown",
                "png": "--dont-generate-png",
                "typst": "--dont-generate-typst",
            }
            for fmt, flag in disable_flags.items():
                if fmt not in requested:
                    args.append(flag)

        with self._semaphore:
            result = self._run(args, cwd=yaml_path.parent)
        artifacts: list[dict] = []

        if output_dir.exists():
            for artifact in output_dir.iterdir():
                if artifact.is_file():
                    artifacts.append(
                        {
                            "type": artifact.suffix.lstrip("."),
                            "filename": artifact.name,
                            "path": str(artifact),
                            "size_bytes": artifact.stat().st_size,
                        }
                    )

        result.artifacts = artifacts
        self.purge_old_jobs()
        return result

    def validate(self, yaml_path: Path) -> CommandResult:
        """
        Validate by running a full render, then discarding all output.
        Errors are captured from stderr.
        """
        tmp_id = "validate_" + self.new_job_id()
        result = self.render(yaml_path, job_id=tmp_id)

        tmp_out = self.workspace_root / "output" / tmp_id
        if tmp_out.exists():
            shutil.rmtree(tmp_out, ignore_errors=True)

        result.artifacts = []
        return result

    def new_resume(self, full_name: str, theme: str = "classic") -> CommandResult:
        output_dir = self.workspace_root / "input"
        args = ["new", full_name, "--theme", theme]
        result = self._run(args, cwd=output_dir)

        slug = full_name.replace(" ", "_")
        expected = output_dir / f"{slug}_CV.yaml"
        if expected.exists():
            result.artifacts = [{"type": "yaml", "filename": expected.name, "path": str(expected)}]

        return result

    def create_theme(
        self, base_theme: str, theme_name: str
    ) -> CommandResult:
        """Scaffold a custom theme based on an existing built-in theme."""
        themes_dir = self.workspace_root / "themes"
        args = ["create-theme", theme_name]
        result = self._run(args, cwd=themes_dir)

        theme_dir = themes_dir / theme_name
        if theme_dir.exists():
            result.artifacts = [
                {
                    "type": "theme_dir",
                    "filename": theme_name,
                    "path": str(theme_dir),
                }
            ]
        return result
