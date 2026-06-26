"""Visual styles for patient DOCX exports."""

from docx.shared import Cm, Pt, RGBColor

FONT_NAME = "Times New Roman"
FONT_BODY_SIZE = Pt(11)
FONT_TABLE_SIZE = Pt(10)
FONT_TITLE_SIZE = Pt(16)
FONT_HEADING_SIZE = Pt(14)
FONT_SUBHEADING_SIZE = Pt(12)

COLOR_PRIMARY = RGBColor(0, 51, 102)
COLOR_WATERMARK = RGBColor(200, 200, 200)
COLOR_MUTED = RGBColor(100, 100, 100)

PAGE_MARGINS = {
    "left": Cm(2.5),
    "right": Cm(2.5),
    "top": Cm(2),
    "bottom": Cm(2),
}

TABLE_STYLE = "Table Grid"
LINE_SPACING = 1.5

DEFAULT_WATERMARK = "MedInsight"
