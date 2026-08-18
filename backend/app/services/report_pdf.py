"""Renders ReportSection/ReportMeta (services/dashboard_report.py) to PDF
bytes via reportlab -- plain layout code, no AI, no network calls."""

import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.dashboard_report import ReportMeta, ReportSection

_INK = colors.HexColor("#101828")
_GREEN = colors.HexColor("#0e2c21")
_MUTED = colors.HexColor("#667085")
_BORDER = colors.HexColor("#eaecf0")

_LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "amara_raja_logo.png"
_LOGO_ASPECT = 202 / 682  # height / width of the source lockup


def _footer(canvas, doc) -> None:
    """Amara Raja branding on every page -- what makes an exported report
    look like it came from a real tenant deployment, not a generic tool."""
    canvas.saveState()
    page_w, _ = A4
    canvas.setStrokeColor(_BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(16 * mm, 14 * mm, page_w - 16 * mm, 14 * mm)

    if _LOGO_PATH.exists():
        logo_w = 26 * mm
        canvas.drawImage(
            str(_LOGO_PATH), 16 * mm, 7.5 * mm, width=logo_w, height=logo_w * _LOGO_ASPECT, mask="auto", preserveAspectRatio=True
        )

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(_MUTED)
    canvas.drawRightString(page_w - 16 * mm, 10 * mm, f"Page {doc.page} · Generated via Enviqo")
    canvas.restoreState()


def build_pdf(sections: list[ReportSection], meta: ReportMeta) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm, leftMargin=16 * mm, rightMargin=16 * mm
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], textColor=_INK, fontSize=20, spaceAfter=2)
    subtitle_style = ParagraphStyle("ReportSubtitle", parent=styles["BodyText"], textColor=_MUTED, fontSize=10)
    section_style = ParagraphStyle("SectionTitle", parent=styles["Heading2"], textColor=_GREEN, spaceBefore=14, spaceAfter=6)
    narrative_style = ParagraphStyle("Narrative", parent=styles["BodyText"], fontSize=10, leading=14, spaceAfter=8)

    story = [Paragraph(meta.title, title_style), Paragraph(meta.subtitle, subtitle_style), Spacer(1, 8)]

    for section in sections:
        story.append(Paragraph(section.title, section_style))
        story.append(Paragraph(section.narrative, narrative_style))

        if section.tiles:
            data = [[t.label, t.value] for t in section.tiles]
            table = Table(data, colWidths=[80 * mm, 80 * mm])
            table.setStyle(
                TableStyle(
                    [
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("TEXTCOLOR", (0, 0), (0, -1), _MUTED),
                        ("TEXTCOLOR", (1, 0), (1, -1), _INK),
                        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
                        ("GRID", (0, 0), (-1, -1), 0.4, _BORDER),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ]
                )
            )
            story.append(table)
            story.append(Spacer(1, 8))

        if section.chart_png:
            img = RLImage(io.BytesIO(section.chart_png), width=170 * mm, height=170 * mm * (2.6 / 6.4))
            story.append(img)

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
