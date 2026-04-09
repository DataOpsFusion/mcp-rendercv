"""
Minimal HTTP file server for artifact downloads.

Runs in a daemon thread alongside the MCP server.
Serves files from workspace/output/ at:

    GET /files/{job_id}/{filename}

Authentication mirrors the MCP server: if RENDERCV_API_KEY is set,
requests must include  Authorization: Bearer <key>.
"""

from __future__ import annotations

import collections
import http.server
import threading
import time
import urllib.parse
from pathlib import Path

from . import config

# Sliding-window rate limiter: max 10 requests per 60 seconds per IP
_RATE_LIMIT_MAX = 10
_RATE_LIMIT_WINDOW = 60.0
_rate_data: dict[str, collections.deque] = {}
_rate_lock = threading.Lock()


def _is_rate_limited(ip: str) -> bool:
    now = time.monotonic()
    with _rate_lock:
        timestamps = _rate_data.setdefault(ip, collections.deque())
        # Evict entries outside the window
        while timestamps and now - timestamps[0] > _RATE_LIMIT_WINDOW:
            timestamps.popleft()
        if len(timestamps) >= _RATE_LIMIT_MAX:
            return True
        timestamps.append(now)
        return False


class _ArtifactHandler(http.server.BaseHTTPRequestHandler):
    output_root: Path  # set as class attribute before starting

    def log_message(self, fmt: str, *args: object) -> None:
        # Suppress default access log noise; errors still surface via log_error
        pass

    def _send_error(self, code: int, message: str) -> None:
        body = message.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_auth(self) -> bool:
        if not config.API_KEY:
            return True
        auth = self.headers.get("Authorization", "")
        return auth == f"Bearer {config.API_KEY}"

    def do_GET(self) -> None:  # noqa: N802
        client_ip = self.client_address[0]
        if _is_rate_limited(client_ip):
            self._send_error(429, "Too Many Requests — max 10 requests per 60 seconds")
            return

        if not self._check_auth():
            self._send_error(401, "Unauthorized")
            return

        # Expect:  /files/<job_id>/<filename>
        path = urllib.parse.unquote(self.path)
        parts = [p for p in path.split("/") if p]

        if len(parts) != 3 or parts[0] != "files":
            self._send_error(404, "Not found — path must be /files/<job_id>/<filename>")
            return

        _, job_id, filename = parts

        # Guard against path traversal
        if ".." in job_id or ".." in filename or "/" in job_id or "/" in filename:
            self._send_error(400, "Invalid path components")
            return

        file_path = self.output_root / job_id / filename
        if not file_path.exists() or not file_path.is_file():
            self._send_error(404, f"Artifact not found: {job_id}/{filename}")
            return

        data = file_path.read_bytes()
        content_type = _content_type(filename)

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header(
            "Content-Disposition", f'attachment; filename="{filename}"'
        )
        self.end_headers()
        self.wfile.write(data)


def _content_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "pdf":  "application/pdf",
        "html": "text/html; charset=utf-8",
        "md":   "text/markdown; charset=utf-8",
        "png":  "image/png",
        "yaml": "text/yaml; charset=utf-8",
        "yml":  "text/yaml; charset=utf-8",
    }.get(ext, "application/octet-stream")


def start(output_root: Path, port: int) -> http.server.HTTPServer:
    """Start the file server in a background daemon thread. Returns the server instance."""

    # Bind output_root to the handler class before the server starts
    handler_cls = type(
        "_BoundArtifactHandler",
        (_ArtifactHandler,),
        {"output_root": output_root},
    )

    server = http.server.HTTPServer(("0.0.0.0", port), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="artifact-fileserver")
    thread.start()
    return server
