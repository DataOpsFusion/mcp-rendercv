# mcp-rendercv

Generate PDF CVs and resumes from structured YAML using the RenderCV engine. Supports multiple themes and YAML validation.

## Tools

| Tool | Description |
|------|-------------|
| `render_cv` | Render a CV from YAML input and return a PDF |
| `list_themes` | List available CV themes |
| `validate_cv` | Validate CV YAML structure before rendering |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `WORKSPACE_DIR` | Directory for temporary render workspaces |
| `PORT` | HTTP port to bind |

## MCP Connection

See `mcp.example.json` for a ready-to-use client configuration.

## CI/CD

Images are built on every push to `main` and pushed to:
- Harbor: `harbor.homeserverlocal.com/mcp/mcp-rendercv:latest`
- Docker Hub: `dataopsfusion/mcp-rendercv:latest`

