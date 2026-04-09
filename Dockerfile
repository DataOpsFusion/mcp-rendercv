# ── Stage 1: builder ─────────────────────────────────────────────────────────
# Use the public Python base image; the Harbor mirror for this tag is not available.
FROM python:3.12-slim AS builder

# uv is fetched from ghcr at build time (Mac has internet; final image does not need it)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml .
COPY rendercv_mcp/ rendercv_mcp/

RUN uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python -e .


# ── Stage 2: runtime ─────────────────────────────────────────────────────────
# RenderCV bundles Typst as a Python package asset — no system Typst install needed.
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY rendercv_mcp/ rendercv_mcp/

ENV RENDERCV_WORKSPACE=/workspace \
    RENDERCV_TRANSPORT=streamable-http \
    RENDERCV_HTTP_HOST=0.0.0.0 \
    RENDERCV_HTTP_PORT=8000 \
    RENDERCV_FILE_SERVER_PORT=8001 \
    PATH="/app/.venv/bin:${PATH}"

VOLUME ["/workspace"]
EXPOSE 8000
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import rendercv" || exit 1

CMD ["python", "-m", "rendercv_mcp"]
