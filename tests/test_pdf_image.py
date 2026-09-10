from pathlib import Path

from PIL import Image

from housebook.services.image_service import ImagePdfService
from housebook.services.pdf_service import PdfService


def test_landscape_and_portrait_images_become_a4(tmp_path: Path) -> None:
    inputs = []
    for name, size in (("landscape.jpg", (1200, 500)), ("portrait.jpg", (500, 1200))):
        image_path = tmp_path / name
        Image.new("RGB", size, "white").save(image_path)
        pdf_path = tmp_path / f"{name}.pdf"
        ImagePdfService().to_a4_pdf(image_path, pdf_path)
        assert PdfService().validate(pdf_path) == 1
        inputs.append(pdf_path)
    merged = tmp_path / "merged.pdf"
    PdfService().merge(inputs, merged)
    assert PdfService().validate(merged) == 2

