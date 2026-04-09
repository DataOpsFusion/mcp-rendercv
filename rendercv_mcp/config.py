"""
Centralised configuration loaded from environment variables.

All tunables live here so __main__.py, server.py, and executor.py
pull from one place instead of scattering os.environ calls.
"""

from __future__ import annotations

import os
from pathlib import Path


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ[key])
    except (KeyError, ValueError):
        return default


# Workspace ---------------------------------------------------------------
WORKSPACE_ROOT = Path(
    os.environ.get("RENDERCV_WORKSPACE", Path.home() / "rendercv-workspace")
).resolve()

# Transport ---------------------------------------------------------------
# "stdio"            — default, for local MCP clients (Claude Desktop)
# "streamable-http"  — for remote / Docker deployments
TRANSPORT = os.environ.get("RENDERCV_TRANSPORT", "stdio")
HTTP_HOST = os.environ.get("RENDERCV_HTTP_HOST", "0.0.0.0")
HTTP_PORT = _env_int("RENDERCV_HTTP_PORT", 8000)

# Auth (HTTP mode only) ---------------------------------------------------
# Set RENDERCV_API_KEY to a non-empty string to require
# "Authorization: Bearer <key>" on every HTTP request.
API_KEY: str | None = os.environ.get("RENDERCV_API_KEY") or None

# CORS (HTTP mode only) ---------------------------------------------------
# Comma-separated list of allowed origins for the MCP transport.
# Defaults to localhost only. Set "*" only for fully trusted internal networks.
_allowed_origins_raw = os.environ.get("RENDERCV_ALLOWED_ORIGINS", "http://localhost")
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _allowed_origins_raw.split(",") if o.strip()]

# Limits ------------------------------------------------------------------
MAX_CONCURRENT_RENDERS = _env_int("RENDERCV_MAX_CONCURRENT_RENDERS", 4)
MAX_YAML_BYTES = _env_int("RENDERCV_MAX_YAML_BYTES", 512_000)  # 512 KB
RENDER_TIMEOUT_SECONDS = _env_int("RENDERCV_RENDER_TIMEOUT", 120)

# Artifact retention ------------------------------------------------------
# Number of most-recent job output directories to keep.
# Set to 0 to disable automatic cleanup.
ARTIFACT_KEEP_JOBS = _env_int("RENDERCV_ARTIFACT_KEEP_JOBS", 50)

# File download server ----------------------------------------------------
# Runs on a separate port alongside the MCP server (HTTP mode only).
# RENDERCV_PUBLIC_URL must be set to the externally reachable base URL of
# the file server, e.g. "http://myserver.com:8001".
# If unset, download_url fields are omitted from render results.
FILE_SERVER_PORT = _env_int("RENDERCV_FILE_SERVER_PORT", 8001)
PUBLIC_URL: str | None = (os.environ.get("RENDERCV_PUBLIC_URL") or "").rstrip("/") or None
