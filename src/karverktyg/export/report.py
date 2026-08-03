"""
Report rendering (§19): one Jinja2 HTML template per report, shared by the
on-screen view and the print output — a print stylesheet, never a second
rendering path that could drift out of sync. WeasyPrint rasterises that HTML to
A4 PDF.

WeasyPrint needs native libs (pango / cairo / gobject) and ships as the optional
``[pdf]`` extra (§3, and the Dockerfile installs it for the deployed container).
The import is therefore **guarded**: where WeasyPrint is absent — a bare test or
dev environment — ``html_to_pdf`` raises :class:`PdfUnavailable`, which the API
turns into a clear "install the [pdf] extra" message instead of a 500. The HTML
render and the Excel exports never touch WeasyPrint, so the offline test suite
stays green with no native dependencies.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATE_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


class PdfUnavailable(RuntimeError):
    """WeasyPrint (the ``[pdf]`` extra + native libs) is not installed here."""


def render_html(template_name: str, context: dict[str, object]) -> str:
    """Render a report template to an HTML string (no native deps)."""
    return _env.get_template(template_name).render(**context)


def html_to_pdf(html: str) -> bytes:
    """
    Rasterise report HTML to A4 PDF bytes via WeasyPrint.

    Raises :class:`PdfUnavailable` when WeasyPrint is not importable, so callers
    can degrade gracefully rather than 500.
    """
    try:
        from weasyprint import HTML
    except ModuleNotFoundError as e:  # pragma: no cover - env-dependent
        raise PdfUnavailable(
            "PDF-rendering kräver WeasyPrint (paketets [pdf]-extra samt "
            "systembiblioteken pango/cairo). Installera med 'uv sync --extra pdf' "
            "eller använd den byggda containern."
        ) from e
    return HTML(string=html).write_pdf()
