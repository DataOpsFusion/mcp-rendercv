"""Entry point — launches the MCP server (stdio or HTTP) and optionally
the artifact file download server on a separate port."""

from __future__ import annotations

import sys

from mcp.server.transport_security import TransportSecuritySettings

from . import config, fileserver
from .server import executor, mcp


def main() -> None:
    ok, version_or_err = executor.health_check()
    if not ok:
        print(
            f"[rendercv-mcp] WARNING: rendercv health check failed: {version_or_err}",
            file=sys.stderr,
        )
    else:
        print(f"[rendercv-mcp] {version_or_err}", file=sys.stderr)

    if config.TRANSPORT == "streamable-http":
        _start_file_server()
        _warn_if_no_api_key()
        mcp.settings.host = config.HTTP_HOST
        mcp.settings.port = config.HTTP_PORT
        # This deployment is intentionally reachable from other LAN clients.
        # Origins restricted via RENDERCV_ALLOWED_ORIGINS (default: http://localhost).
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
            allowed_hosts=["*"],
            allowed_origins=config.ALLOWED_ORIGINS,
        )
        print(
            f"[rendercv-mcp] MCP  → http://{config.HTTP_HOST}:{config.HTTP_PORT}",
            file=sys.stderr,
        )
        mcp.run(transport="streamable-http")
    else:
        print(
            f"[rendercv-mcp] transport=stdio  workspace={config.WORKSPACE_ROOT}",
            file=sys.stderr,
        )
        mcp.run(transport="stdio")


def _start_file_server() -> None:
    output_root = config.WORKSPACE_ROOT / "output"
    output_root.mkdir(parents=True, exist_ok=True)
    fileserver.start(output_root, config.FILE_SERVER_PORT)

    public = config.PUBLIC_URL or f"http://localhost:{config.FILE_SERVER_PORT}"
    print(
        f"[rendercv-mcp] Files → {public}/files/<job_id>/<filename>",
        file=sys.stderr,
    )

    if not config.PUBLIC_URL:
        print(
            "[rendercv-mcp] TIP: set RENDERCV_PUBLIC_URL to the external URL of this "
            "server so download_url fields are included in render results.",
            file=sys.stderr,
        )


def _warn_if_no_api_key() -> None:
    if not config.API_KEY:
        print(
            "[rendercv-mcp] WARNING: RENDERCV_API_KEY is not set — "
            "both the MCP endpoint and the file server are unauthenticated.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
