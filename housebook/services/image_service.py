from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover - optional during core-only tests
    pass


class ImagePdfService:
    MARGIN = 36

    def to_a4_pdf(self, source: Path, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=92, optimize=True)
            buffer.seek(0)
            width, height = image.size
            page_width, page_height = A4
            max_width = page_width - 2 * self.MARGIN
            max_height = page_height - 2 * self.MARGIN
            scale = min(max_width / width, max_height / height)
            draw_width, draw_height = width * scale, height * scale
            x = (page_width - draw_width) / 2
            y = (page_height - draw_height) / 2
            canvas = Canvas(str(destination), pagesize=A4)
            canvas.drawImage(ImageReader(buffer), x, y, draw_width, draw_height, preserveAspectRatio=True, anchor="c")
            canvas.showPage()
            canvas.save()
        return destination

