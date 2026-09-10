from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter


class PdfError(RuntimeError):
    pass


class PdfService:
    def validate(self, path: Path) -> int:
        try:
            reader = PdfReader(str(path))
            count = len(reader.pages)
        except Exception as exc:
            raise PdfError(f"无法读取 PDF：{path.name}") from exc
        if count < 1:
            raise PdfError(f"PDF 没有页面：{path.name}")
        return count

    def merge(self, inputs: list[Path], destination: Path) -> Path:
        if not inputs:
            raise PdfError("没有可合并的 PDF 页面")
        destination.parent.mkdir(parents=True, exist_ok=True)
        writer = PdfWriter()
        for path in inputs:
            self.validate(path)
            reader = PdfReader(str(path))
            for page in reader.pages:
                writer.add_page(page)
        with destination.open("wb") as stream:
            writer.write(stream)
        self.validate(destination)
        return destination
