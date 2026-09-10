from __future__ import annotations

import shutil
import uuid
from datetime import datetime
from pathlib import Path

from ..constants import CAD_SUFFIXES, MATERIAL_BY_CODE, SUPPORTED_SUFFIXES
from ..models import Attachment
from .project_service import ProjectService


class AttachmentError(ValueError):
    pass


class AttachmentService:
    def __init__(self, projects: ProjectService) -> None:
        self.projects = projects

    def add(self, project_id: str, material_code: str, source: Path) -> Attachment:
        if material_code not in MATERIAL_BY_CODE or MATERIAL_BY_CODE[material_code].generated and material_code != "11":
            raise AttachmentError("该材料不接受普通附件")
        suffix = source.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise AttachmentError(f"不支持的文件类型：{suffix}")
        project_root = self.projects.ensure_project_dirs(project_id)
        material_dir = project_root / "attachments" / material_code
        material_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex}{suffix}"
        destination = material_dir / safe_name
        shutil.copy2(source, destination)
        current = [item for item in self.projects.repository.load(project_id).attachments if item.material_code == material_code]
        included = suffix not in CAD_SUFFIXES
        attachment = Attachment(
            project_id=project_id,
            material_code=material_code,
            relative_path=destination.relative_to(self.projects.root).as_posix(),
            file_type=suffix.lstrip("."),
            sort_order=len(current),
            required=MATERIAL_BY_CODE[material_code].required,
            included_in_book=included,
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
        attachment.id = self.projects.repository.add_attachment(attachment)
        return attachment

    def remove(self, attachment: Attachment) -> None:
        if attachment.id is None:
            return
        path = (self.projects.root / attachment.relative_path).resolve()
        attachments_root = (self.projects.project_dir(attachment.project_id) / "attachments").resolve()
        if attachments_root not in path.parents:
            raise AttachmentError("附件路径不在项目目录内")
        if path.exists():
            path.unlink()
        self.projects.repository.remove_attachment(attachment.id)

    def absolute_path(self, attachment: Attachment) -> Path:
        return (self.projects.root / attachment.relative_path).resolve()
