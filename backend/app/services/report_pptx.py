"""Renders ReportSection/ReportMeta (services/dashboard_report.py) to PPTX
bytes via python-pptx -- plain layout code, no AI, no network calls."""

import io

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

from app.services.dashboard_report import ReportMeta, ReportSection

_INK = RGBColor(0x10, 0x18, 0x28)
_GREEN = RGBColor(0x0E, 0x2C, 0x21)
_MUTED = RGBColor(0x66, 0x70, 0x85)


def build_pptx(sections: list[ReportSection], meta: ReportMeta) -> bytes:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    _add_title_slide(prs, blank_layout, meta)
    for section in sections:
        _add_section_slide(prs, blank_layout, section)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _add_title_slide(prs: Presentation, layout, meta: ReportMeta) -> None:
    slide = prs.slides.add_slide(layout)
    title_box = slide.shapes.add_textbox(Inches(0.8), Inches(2.9), Inches(11.7), Inches(1.3))
    p = title_box.text_frame.paragraphs[0]
    p.text = meta.title
    p.font.size = Pt(40)
    p.font.bold = True
    p.font.color.rgb = _INK

    sub_box = slide.shapes.add_textbox(Inches(0.8), Inches(4.0), Inches(11.7), Inches(0.6))
    p = sub_box.text_frame.paragraphs[0]
    p.text = meta.subtitle
    p.font.size = Pt(18)
    p.font.color.rgb = _MUTED


def _add_section_slide(prs: Presentation, layout, section: ReportSection) -> None:
    slide = prs.slides.add_slide(layout)

    title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12.3), Inches(0.7))
    p = title_box.text_frame.paragraphs[0]
    p.text = section.title
    p.font.size = Pt(26)
    p.font.bold = True
    p.font.color.rgb = _GREEN

    narrative_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.05), Inches(12.3), Inches(1.0))
    narrative_box.text_frame.word_wrap = True
    p = narrative_box.text_frame.paragraphs[0]
    p.text = section.narrative
    p.font.size = Pt(13)
    p.font.color.rgb = _INK

    tiles_top = Inches(2.15)
    if section.tiles:
        tile_box = slide.shapes.add_textbox(Inches(0.5), tiles_top, Inches(5.2), Inches(4.8))
        tf = tile_box.text_frame
        tf.word_wrap = True
        for i, tile in enumerate(section.tiles):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = f"{tile.label}:  {tile.value}"
            p.font.size = Pt(15)
            p.font.color.rgb = _INK
            p.space_after = Pt(10)

    if section.chart_png:
        slide.shapes.add_picture(io.BytesIO(section.chart_png), Inches(6.0), tiles_top, width=Inches(6.8))
