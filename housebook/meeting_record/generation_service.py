from __future__ import annotations

import logging
import shutil
from datetime import date
from io import BytesIO
from pathlib import Path

import fitz

from ..logging_utils import safe_event
from ..models import MeetingRecordSnapshot
from ..paths import resource_path
from ..services.pdf_service import PdfService
from ..services.project_service import ProjectService
from .handwriting_engine import HandwritingRenderer
from .layout_engine import MeetingLayoutEngine
from .template_config import MeetingTemplateRegistry


class MeetingRecordGenerationService:
    def __init__(
        self,
        projects: ProjectService,
        registry: MeetingTemplateRegistry | None = None,
        font_path: Path | None = None,
    ) -> None:
        self.projects = projects
        self.registry = registry or MeetingTemplateRegistry()
        self.font_path = (
            font_path or resource_path("fonts", "handwriting", "LXGWWenKaiGBLite-Regular.ttf")
        ).resolve()
        self.pdf = PdfService()
        self.logger = logging.getLogger(__name__)

    def generate(self, project_id: str) -> Path:
        self.projects.ensure_workspace_dirs()
        record = self.projects.repository.load_meeting_record(project_id)
        template = self.registry.get(record.template_id, record.template_version)
        self._preflight(template.first_page_pdf, template.continuation_page_pdf)
        renderer = HandwritingRenderer(self.font_path)
        missing = renderer.missing_characters(self._text_values(record))
        if missing:
            shown = "、".join(missing[:12])
            suffix = "等" if len(missing) > 12 else ""
            raise ValueError(f"手写字体缺少以下字符：{shown}{suffix}")
        layout = MeetingLayoutEngine(template, self.font_path).layout(record)
        run_id = self.projects.repository.start_generation(project_id, False)
        work = self.projects.ensure_project_dirs(project_id) / "temp" / f"meeting-generation-{run_id}"
        work.mkdir(parents=True, exist_ok=True)
        rendered = work / "meeting-record.pdf"
        try:
            self._compose_pdf(record, template, renderer, layout.placements, layout.page_count, rendered)
            self._validate_a4(rendered, layout.page_count)
            filename = f"{self._safe_filename(record.meeting_name or '未命名')}_会议记录_{date.today():%Y%m%d}.pdf"
            output = self.projects.output_path(filename)
            shutil.copy2(rendered, output)
            record.output_pdf_path = output.relative_to(self.projects.root).as_posix()
            record.status = "completed"
            self.projects.repository.save_meeting_record(record)
            relative = output.relative_to(self.projects.root).as_posix()
            self.projects.repository.finish_generation(run_id, output_path=relative, output_format="pdf")
            safe_event(self.logger, "meeting_record_generation_completed", project_id=project_id)
            return output
        except Exception as exc:
            self.projects.repository.finish_generation(
                run_id, output_format="pdf", error_type=type(exc).__name__
            )
            safe_event(
                self.logger,
                "meeting_record_generation_failed",
                project_id=project_id,
                error_type=type(exc).__name__,
            )
            raise

    @staticmethod
    def _text_values(record: MeetingRecordSnapshot) -> list[str]:
        return [
            record.meeting_name,
            record.meeting_time,
            record.location,
            "" if record.expected_count is None else str(record.expected_count),
            "" if record.actual_count is None else str(record.actual_count),
            record.participants,
            record.observers,
            record.chairperson,
            record.recorder,
            record.topic,
            record.content,
        ]

    def _preflight(self, first_page: Path, continuation_page: Path) -> None:
        if not self.font_path.is_file():
            raise RuntimeError("手写字体文件缺失，请重新安装应用")
        for path in (first_page, continuation_page):
            if not path.is_file():
                raise RuntimeError("会议记录模板不完整，请重新安装应用")
            self.pdf.validate(path)

    @staticmethod
    def _compose_pdf(record, template, renderer, placements, page_count: int, destination: Path) -> None:
        first = fitz.open(template.first_page_pdf)
        continuation = fitz.open(template.continuation_page_pdf)
        output = fitz.open()
        try:
            for page_index in range(page_count):
                base = first if page_index == 0 else continuation
                source_page = base[0]
                page = output.new_page(width=source_page.rect.width, height=source_page.rect.height)
                page.show_pdf_page(page.rect, base, 0)
                layer = renderer.render_page(
                    placements,
                    page_index,
                    template.page_width_mm,
                    template.page_height_mm,
                    record.handwriting_seed,
                )
                buffer = BytesIO()
                layer.save(buffer, format="PNG", optimize=True)
                page.insert_image(page.rect, stream=buffer.getvalue(), overlay=True, keep_proportion=False)
                layer.close()
            destination.parent.mkdir(parents=True, exist_ok=True)
            output.save(destination, garbage=3, deflate=True)
        finally:
            output.close()
            first.close()
            continuation.close()

    def _validate_a4(self, path: Path, expected_pages: int) -> None:
        if self.pdf.validate(path) != expected_pages:
            raise RuntimeError("会议记录 PDF 页数校验失败")
        expected_width = 210.0 * 72.0 / 25.4
        expected_height = 297.0 * 72.0 / 25.4
        with fitz.open(path) as document:
            for page in document:
                if abs(page.rect.width - expected_width) > 1 or abs(page.rect.height - expected_height) > 1:
                    raise RuntimeError("会议记录 PDF 纸张尺寸不是 A4")

    @staticmethod
    def _safe_filename(name: str) -> str:
        invalid = '<>:"/\\|?*'
        sanitized = "".join("_" if char in invalid else char for char in name).strip(" .")
        return sanitized[:80] or "未命名"
