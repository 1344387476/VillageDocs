from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..constants import (
    BOOK_ORDER, GENERATED_CODES, IMAGE_SUFFIXES, MATERIAL_BY_CODE, PDF_SUFFIXES,
    REQUIRED_ATTACHMENT_CODES, WORD_SUFFIXES,
)
from ..logging_utils import safe_event
from ..models import Attachment, ProjectSnapshot
from .attachment_service import AttachmentService
from .libreoffice_service import LibreOfficeService
from .pdf_service import PdfService
from .project_service import ProjectService
from .template_service import TemplateService
from .word_service import WordBookService


@dataclass(frozen=True, slots=True)
class MissingMaterial:
    material_code: str
    name: str
    reason: str


class GenerationService:
    def __init__(
        self,
        projects: ProjectService,
        templates: TemplateService,
        attachments: AttachmentService,
        converter: LibreOfficeService,
    ) -> None:
        self.projects = projects
        self.templates = templates
        self.attachments = attachments
        self.converter = converter
        self.word = WordBookService()
        self.pdf = PdfService()
        self.logger = logging.getLogger(__name__)

    def preflight(self) -> None:
        self.word.preflight()
        if not self.converter.available():
            raise RuntimeError("内置文档转换组件不完整，请重新安装村务材料管理 1.1")
        missing_templates = [item.template for item in self.templates.manifests() if not (self.templates.template_dir / item.template).is_file()]
        if missing_templates:
            raise RuntimeError("材料模板不完整，请重新安装村务材料管理 1.1")

    def missing_materials(self, snapshot: ProjectSnapshot) -> list[MissingMaterial]:
        present = {item.material_code for item in snapshot.attachments if item.included_in_book}
        missing = [
            MissingMaterial(code, MATERIAL_BY_CODE[code].name, "尚未上传")
            for code in REQUIRED_ATTACHMENT_CODES if code not in present
        ]
        notice_photos = [item for item in snapshot.attachments if item.material_code == "11" and item.included_in_book]
        if len(notice_photos) < 2:
            missing.append(MissingMaterial("11", MATERIAL_BY_CODE["11"].name, "需要远景、近景照片各一张"))
        return missing

    def generate(
        self,
        project_id: str,
        *,
        output_format: str = "docx",
        allow_incomplete: bool = False,
    ) -> Path:
        if output_format not in {"docx", "pdf"}:
            raise ValueError(f"不支持的输出格式：{output_format}")
        self.preflight()
        # The install-side resource folder may have been removed after startup.
        # Recreate it and its required subdirectories when the user generates.
        self.projects.ensure_workspace_dirs()
        snapshot = self.projects.repository.load(project_id)
        missing = self.missing_materials(snapshot)
        if missing and not allow_incomplete:
            details = "；".join(f"{item.material_code} {item.name}" for item in missing)
            raise ValueError(f"缺少必需材料：{details}")
        run_id = self.projects.repository.start_generation(project_id, bool(missing))
        project_root = self.projects.ensure_project_dirs(project_id)
        work = project_root / "temp" / f"generation-{run_id}"
        work.mkdir(parents=True, exist_ok=True)
        try:
            components = self._components(snapshot, work)
            composed_docx = self.word.compose(components, work / "complete-book.docx")
            safe_name = self._safe_filename(snapshot.applicant.name or "未命名")
            incomplete_suffix = "_未完整" if missing else ""
            filename = f"{safe_name}_村民建房报备材料_{date.today():%Y%m%d}{incomplete_suffix}.{output_format}"
            output = self.projects.output_path(filename)
            if output_format == "docx":
                shutil.copy2(composed_docx, output)
                snapshot.output_docx_path = output.relative_to(self.projects.root).as_posix()
            else:
                rendered_pdf = self.converter.to_pdf(composed_docx, work / "pdf")
                self.pdf.validate(rendered_pdf)
                shutil.copy2(rendered_pdf, output)
                snapshot.output_pdf_path = output.relative_to(self.projects.root).as_posix()
            snapshot.last_output_format = output_format
            snapshot.status = "incomplete" if missing else "completed"
            self.projects.repository.save(snapshot)
            relative_output = output.relative_to(self.projects.root).as_posix()
            self.projects.repository.finish_generation(
                run_id,
                output_path=relative_output,
                output_format=output_format,
            )
            safe_event(self.logger, f"generation_completed_{output_format}", project_id=project_id)
            return output
        except Exception as exc:
            self.projects.repository.finish_generation(
                run_id,
                output_format=output_format,
                error_type=type(exc).__name__,
            )
            safe_event(self.logger, "generation_failed", project_id=project_id, error_type=type(exc).__name__)
            raise

    def _components(self, snapshot: ProjectSnapshot, work: Path) -> list[Path]:
        by_code: dict[str, list[Path]] = {}
        for code in GENERATED_CODES:
            by_code[code] = [self.templates.render(code, snapshot, work / code)]

        attachments_by_code: dict[str, list[Attachment]] = {}
        ordered_attachments = sorted(
            snapshot.attachments,
            key=lambda item: (int(item.material_code), item.sort_order, item.id or 0),
        )
        for attachment in ordered_attachments:
            if attachment.included_in_book:
                attachments_by_code.setdefault(attachment.material_code, []).append(attachment)

        for code, items in attachments_by_code.items():
            output_dir = work / code / "attachments"
            if code == "09":
                id_images = [
                    self.attachments.absolute_path(item)
                    for item in items
                    if Path(item.relative_path).suffix.lower() in IMAGE_SUFFIXES
                ]
                if id_images:
                    by_code.setdefault(code, []).append(
                        self.word.id_card_component(id_images, output_dir / "id-cards.docx")
                    )
                items = [
                    item for item in items
                    if Path(item.relative_path).suffix.lower() not in IMAGE_SUFFIXES
                ]
            for item in items:
                by_code.setdefault(code, []).append(self._attachment_component(item, output_dir))

        return [path for code in BOOK_ORDER for path in by_code.get(code, [])]

    def _attachment_component(self, attachment: Attachment, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        source = self.attachments.absolute_path(attachment)
        suffix = source.suffix.lower()
        stem = f"attachment-{attachment.id}"
        if suffix in PDF_SUFFIXES:
            return self.word.pdf_component(source, output_dir, stem)
        if suffix in IMAGE_SUFFIXES:
            return self.word.image_pages_component([source], output_dir / f"{stem}.docx")
        if suffix in WORD_SUFFIXES:
            docx_path = source if suffix == ".docx" else self.converter.to_docx(source, output_dir)
            if self.word.safe_editable_docx(docx_path):
                return docx_path
            pdf_path = self.converter.to_pdf(source, output_dir / f"{stem}-pdf")
            return self.word.pdf_component(pdf_path, output_dir, f"{stem}-raster")
        raise ValueError(f"文件不参与成册：{source.name}")

    @staticmethod
    def _safe_filename(name: str) -> str:
        invalid = '<>:"/\\|?*'
        sanitized = "".join("_" if char in invalid else char for char in name).strip(" .")
        return sanitized[:80] or "未命名"
