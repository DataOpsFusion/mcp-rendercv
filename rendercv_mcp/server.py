"""
RenderCV MCP Server — Full implementation (Phases 1-3)

Tools
─────
  rendercv_render              Render YAML → PDF / HTML / Markdown / PNG
  rendercv_validate            Validate YAML without keeping output
  rendercv_new_resume          Scaffold a starter YAML file
  rendercv_list_themes         List built-in themes
  rendercv_create_theme        Scaffold a custom theme
  rendercv_list_artifacts      List artifacts from a past render job
  rendercv_read_artifact       Read a text artifact (HTML / Markdown)

Resources
─────────
  rendercv://schema                         Full JSON schema
  rendercv://examples/starter               Minimal working YAML
  rendercv://artifacts/{job_id}/{filename}  A generated artifact file

Prompts
───────
  resume-from-bullets
  improve-rendercv-yaml
  tailor-resume-for-job
  convert-notes-to-section
"""

from __future__ import annotations

import base64
import json
from typing import Literal

from mcp.server.fastmcp import FastMCP

from . import config
from .executor import RenderCVExecutor, WorkspaceViolation


def _with_download_urls(artifacts: list[dict], job_id: str) -> list[dict]:
    """Attach a download_url to each artifact when PUBLIC_URL is configured."""
    if not config.PUBLIC_URL:
        return artifacts
    result = []
    for a in artifacts:
        entry = dict(a)
        filename = a.get("filename")
        if filename:
            entry["download_url"] = f"{config.PUBLIC_URL}/files/{job_id}/{filename}"
        result.append(entry)
    return result

# ------------------------------------------------------------------
# Bootstrap
# ------------------------------------------------------------------

executor = RenderCVExecutor(config.WORKSPACE_ROOT)

mcp = FastMCP(
    "rendercv-mcp",
    instructions=(
        "Use rendercv_render to generate PDF/HTML/Markdown resumes from RenderCV YAML. "
        "Use rendercv_validate to check YAML before rendering. "
        "Use rendercv_new_resume to scaffold a starter YAML. "
        "The rendercv://schema resource contains the full JSON schema for YAML authoring. "
        "After rendering, use rendercv_list_artifacts to see generated files, or access "
        "them directly via rendercv://artifacts/{job_id}/{filename}."
    ),
)

# ------------------------------------------------------------------
# Tools — rendering
# ------------------------------------------------------------------

@mcp.tool()
def rendercv_render(
    input_mode: Literal["path", "inline"],
    yaml_path: str | None = None,
    yaml_content: str | None = None,
    formats: list[str] | None = None,
) -> dict:
    """
    Render a RenderCV YAML resume into PDF, HTML, Markdown, or PNG.

    Args:
        input_mode:   'path' to reference a workspace file, or 'inline' for raw YAML.
        yaml_path:    Absolute path inside the workspace (required for 'path' mode).
        yaml_content: Raw YAML string (required for 'inline' mode).
        formats:      Output formats to request — ['pdf', 'html', 'markdown', 'png'].
                      Omit to use RenderCV's default (pdf + html + markdown).
    """
    try:
        job_id = executor.new_job_id()

        if input_mode == "inline":
            if not yaml_content:
                return {"ok": False, "error": "yaml_content is required for inline mode"}
            resolved_path = executor.write_inline_yaml(yaml_content, job_id)
        else:
            if not yaml_path:
                return {"ok": False, "error": "yaml_path is required for path mode"}
            resolved_path = executor.resolve_yaml_path(yaml_path)

        result = executor.render(resolved_path, job_id=job_id, formats=formats)

        return {
            "ok": result.ok,
            "job_id": job_id,
            "artifacts": _with_download_urls(result.artifacts, job_id),
            "stdout": result.stdout[-3000:] if result.stdout else "",
            "stderr": result.stderr[-3000:] if result.stderr else "",
        }

    except WorkspaceViolation as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@mcp.tool()
def rendercv_validate(
    input_mode: Literal["path", "inline"],
    yaml_path: str | None = None,
    yaml_content: str | None = None,
) -> dict:
    """
    Validate a RenderCV YAML file without keeping the rendered output.

    Returns validation status and structured error/warning lists.

    Args:
        input_mode:   'path' or 'inline'.
        yaml_path:    Absolute workspace path (for 'path' mode).
        yaml_content: Raw YAML string (for 'inline' mode).
    """
    try:
        job_id = executor.new_job_id()

        if input_mode == "inline":
            if not yaml_content:
                return {
                    "ok": False,
                    "valid": False,
                    "error": "yaml_content is required for inline mode",
                }
            resolved_path = executor.write_inline_yaml(yaml_content, job_id)
        else:
            if not yaml_path:
                return {
                    "ok": False,
                    "valid": False,
                    "error": "yaml_path is required for path mode",
                }
            resolved_path = executor.resolve_yaml_path(yaml_path)

        result = executor.validate(resolved_path)

        return {
            "ok": result.ok,
            "valid": result.ok,
            "errors": _extract_errors(result.stderr),
            "warnings": _extract_warnings(result.stderr),
            "raw_stderr": result.stderr[-3000:] if result.stderr else "",
        }

    except WorkspaceViolation as e:
        return {"ok": False, "valid": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "valid": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "valid": False, "error": f"Unexpected error: {e}"}


# ------------------------------------------------------------------
# Tools — resume management
# ------------------------------------------------------------------

@mcp.tool()
def rendercv_new_resume(
    full_name: str,
    theme: str = "classic",
) -> dict:
    """
    Scaffold a new starter RenderCV YAML file for the given person.

    Args:
        full_name: The person's full name, e.g. 'Jane Smith'.
        theme:     RenderCV theme to scaffold with. Run rendercv_list_themes
                   to see available options. Defaults to 'classic'.
    """
    try:
        result = executor.new_resume(full_name, theme=theme)
        return {
            "ok": result.ok,
            "artifacts": result.artifacts,
            "stdout": result.stdout[-3000:] if result.stdout else "",
            "stderr": result.stderr[-3000:] if result.stderr else "",
        }
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@mcp.tool()
def rendercv_list_themes() -> dict:
    """List the built-in RenderCV themes available for rendering."""
    return {
        "ok": True,
        "themes": [
            {
                "name": "classic",
                "description": "Clean, traditional single-column layout.",
            },
            {
                "name": "ember",
                "description": "Warm accent styling with modern section treatment.",
            },
            {
                "name": "engineeringclassic",
                "description": "Classic engineering-focused resume format.",
            },
            {
                "name": "moderncv",
                "description": "Modern two-tone header, inspired by the LaTeX moderncv package.",
            },
            {
                "name": "sb2nov",
                "description": "Compact academic / engineering style.",
            },
            {
                "name": "engineeringresumes",
                "description": "Dense, ATS-friendly single-column format popular in tech.",
            },
            {
                "name": "harvard",
                "description": "Traditional academic layout with conservative typography.",
            },
            {
                "name": "ink",
                "description": "Minimal high-contrast design with understated styling.",
            },
            {
                "name": "opal",
                "description": "Contemporary layout with softer visual treatment.",
            },
        ],
        "note": (
            "Custom themes can be scaffolded with rendercv_create_theme "
            "and stored in workspace/themes/."
        ),
    }


@mcp.tool()
def rendercv_create_theme(
    theme_name: str,
    base_theme: str = "classic",
) -> dict:
    """
    Scaffold a custom RenderCV theme based on an existing built-in theme.

    The theme files are created inside workspace/themes/<theme_name>/.
    Edit the Jinja2 / Typst templates there, then reference the theme
    name in your YAML's design.theme field.

    Args:
        theme_name: Name for the new custom theme directory.
        base_theme: Built-in theme to derive from. Defaults to 'classic'.
    """
    try:
        result = executor.create_theme(base_theme, theme_name)
        return {
            "ok": result.ok,
            "artifacts": result.artifacts,
            "stdout": result.stdout[-3000:] if result.stdout else "",
            "stderr": result.stderr[-3000:] if result.stderr else "",
        }
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


# ------------------------------------------------------------------
# Tools — artifact access
# ------------------------------------------------------------------

@mcp.tool()
def rendercv_list_artifacts(job_id: str) -> dict:
    """
    List the output files generated by a previous render job.

    Args:
        job_id: The job_id returned by rendercv_render.
    """
    try:
        artifacts = executor.list_job_artifacts(job_id)
        return {"ok": True, "job_id": job_id, "artifacts": _with_download_urls(artifacts, job_id)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@mcp.tool()
def rendercv_read_artifact(job_id: str, filename: str) -> dict:
    """
    Read a text artifact (HTML or Markdown) produced by a render job.

    For PDF and PNG files, use the file path returned by rendercv_render
    to open them locally — they cannot be returned as text.

    Args:
        job_id:   The job_id returned by rendercv_render.
        filename: The artifact filename, e.g. 'resume_cv.html'.
    """
    try:
        data = executor.read_artifact(job_id, filename)

        if filename.endswith((".html", ".md", ".txt", ".yaml", ".yml")):
            return {
                "ok": True,
                "job_id": job_id,
                "filename": filename,
                "encoding": "utf-8",
                "content": data.decode("utf-8", errors="replace"),
            }
        else:
            return {
                "ok": True,
                "job_id": job_id,
                "filename": filename,
                "encoding": "base64",
                "content": base64.b64encode(data).decode("ascii"),
                "note": "Binary file returned as base64. Open the path directly for best results.",
            }
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except WorkspaceViolation as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


# ------------------------------------------------------------------
# Resources
# ------------------------------------------------------------------

@mcp.resource("rendercv://schema")
def schema_resource() -> str:
    """The current RenderCV JSON schema for YAML validation and authoring."""
    try:
        import rendercv.data as rcdata  # type: ignore
        from pathlib import Path as _Path

        schema_path = _Path(rcdata.__file__).parent / "json_schema.json"
        if schema_path.exists():
            return schema_path.read_text(encoding="utf-8")

        import importlib.resources as ir
        return ir.read_text("rendercv.data", "json_schema.json")  # type: ignore
    except Exception as e:
        return json.dumps({"error": f"Could not load schema: {e}"})


@mcp.resource("rendercv://examples/starter")
def example_starter_resource() -> str:
    """A minimal working RenderCV YAML example to get started."""
    return """\
cv:
  name: Jane Smith
  location: San Francisco, CA
  email: jane@example.com
  phone: "+1 (555) 000-0000"
  website: https://github.com/janesmith
  sections:
    education:
      - institution: University of California, Berkeley
        area: Computer Science
        degree: BS
        start_date: 2018-09
        end_date: 2022-05
        highlights:
          - "GPA: 3.9 / 4.0"
    experience:
      - company: Acme Corp
        position: Software Engineer
        location: San Francisco, CA
        start_date: 2022-06
        end_date: present
        highlights:
          - Reduced API latency by 40% by migrating to async request handling.
          - Led a team of 3 engineers to ship a new billing pipeline on schedule.
    skills:
      - label: Languages
        details: Python, TypeScript, Go, SQL
      - label: Tools
        details: Docker, Kubernetes, PostgreSQL, Redis
design:
  theme: classic
"""


@mcp.resource("rendercv://artifacts/{job_id}/{filename}")
def artifact_resource(job_id: str, filename: str) -> str:
    """
    A generated artifact file from a render job.

    Text files (HTML, Markdown) are returned directly.
    Binary files are base64-encoded.
    """
    try:
        data = executor.read_artifact(job_id, filename)
        if filename.endswith((".html", ".md", ".txt")):
            return data.decode("utf-8", errors="replace")
        return base64.b64encode(data).decode("ascii")
    except (FileNotFoundError, WorkspaceViolation) as e:
        return json.dumps({"error": str(e)})


# ------------------------------------------------------------------
# Prompts
# ------------------------------------------------------------------

@mcp.prompt()
def resume_from_bullets(
    name: str,
    bullets: str,
    theme: str = "classic",
) -> str:
    """
    Convert freeform experience notes into a complete RenderCV YAML resume.

    Args:
        name:    Full name of the person.
        bullets: Freeform text with experience, education, and skill notes.
        theme:   RenderCV theme (classic, moderncv, sb2nov, engineeringresumes).
    """
    return f"""\
Convert the following experience notes into a complete, valid RenderCV YAML resume.

Person: {name}
Theme: {theme}

Experience notes:
{bullets}

Rules:
- Output ONLY valid YAML — no prose, no markdown fences.
- Follow the RenderCV schema exactly. Schema: rendercv://schema
- Use the starter at rendercv://examples/starter as a structural reference.
- Dates must be ISO format: YYYY-MM or YYYY-MM-DD. Use "present" for current roles.
- Each highlight must be a concrete, quantified achievement where possible.
- Do not invent facts. Omit fields where information is missing.
- Set design.theme to "{theme}".
"""


@mcp.prompt()
def improve_rendercv_yaml(
    yaml_content: str,
    focus: Literal["impact", "conciseness", "ats"] = "impact",
) -> str:
    """
    Improve an existing RenderCV YAML resume.

    Args:
        yaml_content: The current YAML to improve.
        focus:        'impact' — quantify outcomes; 'conciseness' — cut filler;
                      'ats' — normalise terminology for ATS systems.
    """
    instructions = {
        "impact": (
            "Rewrite bullet points to lead with strong action verbs and include "
            "quantified outcomes (%, $, time saved, users affected) wherever possible."
        ),
        "conciseness": (
            "Trim each bullet to one punchy line. Remove filler words. "
            "Cut anything that doesn't add signal for a hiring manager."
        ),
        "ats": (
            "Ensure job titles, skill names, and section headings use standard industry "
            "terminology. Avoid abbreviations that ATS systems may not recognise."
        ),
    }

    return f"""\
Improve the following RenderCV YAML resume.

Focus: {focus}
Instruction: {instructions[focus]}

Rules:
- Output ONLY the improved YAML — no prose, no markdown fences.
- Preserve the exact RenderCV schema structure. Do not add or remove top-level keys.
- Do not change the person's name, employer names, dates, or education institutions.
- Validate your output mentally against the schema at rendercv://schema before responding.

Current YAML:
{yaml_content}
"""


@mcp.prompt()
def tailor_resume_for_job(
    yaml_content: str,
    job_description: str,
) -> str:
    """
    Tailor an existing RenderCV YAML resume to a specific job description.

    Args:
        yaml_content:    The current YAML resume.
        job_description: The full text of the target job posting.
    """
    return f"""\
Tailor the following RenderCV YAML resume to the job description below.

What to do:
1. Reorder or rename skills to match the job's keywords.
2. Emphasise highlights that are most relevant to the role.
3. Add any clearly implied skills the person likely has based on their experience.
4. Do NOT fabricate experience, titles, dates, or companies.

Rules:
- Output ONLY valid YAML — no prose, no markdown fences.
- Preserve the full RenderCV schema structure.
- Keep all factual information (names, dates, employers) unchanged.
- Schema reference: rendercv://schema

Job description:
{job_description}

Current YAML:
{yaml_content}
"""


@mcp.prompt()
def convert_notes_to_section(
    section_type: Literal["experience", "education", "skills", "projects", "publications"],
    notes: str,
) -> str:
    """
    Convert freeform notes into a single valid RenderCV YAML section.

    Useful for building up a resume section-by-section.

    Args:
        section_type: The RenderCV section type to generate.
        notes:        Freeform notes describing entries in this section.
    """
    type_hints = {
        "experience": (
            "Each entry needs: company, position, location, start_date, end_date, highlights. "
            "highlights is a list of bullet strings."
        ),
        "education": (
            "Each entry needs: institution, area, degree, start_date, end_date. "
            "Optional: highlights, gpa."
        ),
        "skills": (
            "Each entry needs: label, details. "
            "label is a category name; details is a comma-separated string of skills."
        ),
        "projects": (
            "Each entry needs: name, date, highlights. "
            "Optional: url."
        ),
        "publications": (
            "Each entry needs: title, authors, date, journal. "
            "Optional: doi, url."
        ),
    }

    return f"""\
Convert the following notes into a valid RenderCV YAML section of type '{section_type}'.

Schema hint for this section type:
{type_hints[section_type]}

Full schema for reference: rendercv://schema

Rules:
- Output ONLY the YAML for this section — not a full resume document.
- Start with the section key, e.g.:
    {section_type}:
      - ...
- Dates must be ISO format: YYYY-MM. Use "present" for current entries.
- Do not invent facts.

Notes:
{notes}
"""


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _extract_errors(stderr: str) -> list[str]:
    if not stderr:
        return []
    return [
        line.strip()
        for line in stderr.splitlines()
        if any(kw in line.lower() for kw in ("error", "invalid", "failed", "traceback"))
    ]


def _extract_warnings(stderr: str) -> list[str]:
    if not stderr:
        return []
    return [
        line.strip()
        for line in stderr.splitlines()
        if "warning" in line.lower()
    ]
