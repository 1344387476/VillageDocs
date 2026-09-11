from __future__ import annotations

import hashlib
import json
from pathlib import Path

import fitz
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "resources" / "templates" / "meeting_record" / "v1"
PRINT_FONT = ROOT / "tools" / "assets" / "fonts" / "NotoSerifSC[wght].ttf"
PRINT_FONT_LICENSE = ROOT / "tools" / "assets" / "fonts" / "OFL-NotoSerifSC.txt"
RUNTIME_PRINT_LICENSE = ROOT / "resources" / "fonts" / "print" / "OFL-NotoSerifSC.txt"
HANDWRITING_FONT = (
    ROOT / "resources" / "fonts" / "handwriting" / "LXGWWenKaiGBLite-Regular.ttf"
)
HANDWRITING_LICENSE = ROOT / "resources" / "fonts" / "handwriting" / "OFL.txt"
FONT_NAME = "MeetingPrint"
PAGE_HEIGHT_MM = 297.0


def _y(top_mm: float) -> float:
    return (PAGE_HEIGHT_MM - top_mm) * mm


def _draw_text(canvas: Canvas, text: str, x_mm: float, baseline_mm: float, size: float) -> None:
    canvas.setFont(FONT_NAME, size)
    canvas.drawString(x_mm * mm, _y(baseline_mm), text)


def _draw_first_page(path: Path) -> None:
    canvas = Canvas(str(path), pagesize=A4, pageCompression=1)
    canvas.setTitle("标准会议记录模板 - 第一页")
    canvas.setCreator("村务材料管理")
    canvas.setFillColorRGB(0.08, 0.09, 0.10)
    canvas.setStrokeColorRGB(0.13, 0.15, 0.17)
    canvas.setLineWidth(0.42)

    left, right = 24.2, 186.1
    table_lines = (
        45.7, 55.9, 66.1, 76.6, 86.7, 97.2, 107.5, 117.7, 127.7,
        137.9, 148.0, 158.2, 168.0, 178.3, 188.3, 198.5, 208.6,
        218.5, 228.7, 238.6, 248.7, 258.3,
    )
    for line_y in table_lines:
        canvas.line(left * mm, _y(line_y), right * mm, _y(line_y))
    canvas.line(left * mm, _y(table_lines[0]), left * mm, _y(table_lines[-1]))
    canvas.line(right * mm, _y(table_lines[0]), right * mm, _y(table_lines[-1]))

    _draw_text(canvas, "会议名称：", 39.0, 42.6, 18)
    canvas.setLineWidth(0.48)
    canvas.line(78.5 * mm, _y(44.2), 173.8 * mm, _y(44.2))
    canvas.setLineWidth(0.42)

    labels = (
        ("时  间：", 27.0, 53.0),
        ("地  点：", 99.5, 53.0),
        ("应到会人数：", 27.0, 63.2),
        ("实到会人数：", 99.5, 63.2),
        ("参加人员：", 27.0, 73.5),
        ("列席人员：", 27.0, 135.0),
        ("主持人：", 27.0, 145.2),
        ("记录人：", 99.5, 145.2),
        ("主  题：", 27.0, 155.4),
        ("主要内容：", 27.0, 175.5),
    )
    for text, x, baseline in labels:
        _draw_text(canvas, text, x, baseline, 11.5)
    canvas.showPage()
    canvas.save()


def _draw_continuation_page(path: Path) -> None:
    canvas = Canvas(str(path), pagesize=A4, pageCompression=1)
    canvas.setTitle("标准会议记录模板 - 续页")
    canvas.setCreator("村务材料管理")
    canvas.setStrokeColorRGB(0.13, 0.15, 0.17)
    canvas.setLineWidth(0.42)
    left, right = 25.1, 185.4
    lines = (
        34.1, 43.9, 53.8, 63.8, 74.0, 84.2, 94.4, 104.7, 114.9,
        125.4, 135.6, 146.1, 156.6, 166.8, 177.3, 187.7, 198.2,
        208.4, 218.6, 228.8, 239.0, 249.0, 258.5,
    )
    for line_y in lines:
        canvas.line(left * mm, _y(line_y), right * mm, _y(line_y))
    canvas.line(left * mm, _y(lines[0]), left * mm, _y(lines[-1]))
    canvas.line(right * mm, _y(lines[0]), right * mm, _y(lines[-1]))
    canvas.showPage()
    canvas.save()


def _thumbnail(pdf_path: Path, output: Path) -> None:
    with fitz.open(pdf_path) as document:
        pixmap = document[0].get_pixmap(matrix=fitz.Matrix(0.55, 0.55), alpha=False)
        pixmap.save(output)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_inventory() -> None:
    tracked = (
        TEMPLATE_DIR / "source" / "page-1-reference.jpg",
        TEMPLATE_DIR / "source" / "page-2-reference.jpg",
        TEMPLATE_DIR / "template.json",
        TEMPLATE_DIR / "first_page.pdf",
        TEMPLATE_DIR / "continuation_page.pdf",
        TEMPLATE_DIR / "thumbnail.png",
        HANDWRITING_FONT,
        HANDWRITING_LICENSE,
        PRINT_FONT,
        PRINT_FONT_LICENSE,
        RUNTIME_PRINT_LICENSE,
    )
    payload = {
        "template_id": "standard_meeting_record",
        "template_version": 1,
        "generated_by": "tools/prepare_meeting_templates.py",
        "files": {
            path.relative_to(ROOT).as_posix(): {
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in tracked
        },
    }
    (TEMPLATE_DIR / "template_inventory.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    required = (
        PRINT_FONT,
        PRINT_FONT_LICENSE,
        HANDWRITING_FONT,
        HANDWRITING_LICENSE,
        RUNTIME_PRINT_LICENSE,
        TEMPLATE_DIR / "source" / "page-1-reference.jpg",
        TEMPLATE_DIR / "source" / "page-2-reference.jpg",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("会议模板资源缺失：" + "、".join(missing))
    pdfmetrics.registerFont(TTFont(FONT_NAME, str(PRINT_FONT), subfontIndex=0))
    _draw_first_page(TEMPLATE_DIR / "first_page.pdf")
    _draw_continuation_page(TEMPLATE_DIR / "continuation_page.pdf")
    _thumbnail(TEMPLATE_DIR / "first_page.pdf", TEMPLATE_DIR / "thumbnail.png")
    _write_inventory()
    print(f"会议记录模板已生成：{TEMPLATE_DIR}")


if __name__ == "__main__":
    main()
