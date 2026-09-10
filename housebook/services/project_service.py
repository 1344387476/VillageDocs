from __future__ import annotations

import shutil
from pathlib import Path

from send2trash import send2trash

from ..models import ProjectSnapshot
from ..repository import ProjectRepository


class ProjectService:
    def __init__(self, workspace_root: Path) -> None:
        self.root = workspace_root.resolve()
        self.ensure_workspace_dirs()
        self.repository = ProjectRepository(self.root / "data" / "app.db")

    def ensure_workspace_dirs(self) -> Path:
        """Create the resource workspace again if it is not present."""
        self.root.mkdir(parents=True, exist_ok=True)
        for folder in ("data", "projects", "exports", "logs"):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        return self.root

    def project_dir(self, project_id: str) -> Path:
        path = (self.root / "projects" / project_id).resolve()
        if path.parent != (self.root / "projects").resolve():
            raise ValueError("非法项目路径")
        return path

    def create_project(self, material_type: str = "village_house") -> ProjectSnapshot:
        snapshot = self.repository.create_project(material_type)
        root = self.project_dir(snapshot.id)
        for folder in ("attachments", "generated", "temp"):
            (root / folder).mkdir(parents=True, exist_ok=True)
        return snapshot

    def ensure_project_dirs(self, project_id: str) -> Path:
        self.ensure_workspace_dirs()
        root = self.project_dir(project_id)
        for folder in ("attachments", "generated", "temp"):
            (root / folder).mkdir(parents=True, exist_ok=True)
        return root

    def delete_project_to_recycle_bin(self, project_id: str) -> None:
        root = self.project_dir(project_id)
        if root.exists():
            send2trash(str(root))
        self.repository.delete_project_record(project_id)

    def output_path(self, filename: str) -> Path:
        self.ensure_workspace_dirs()
        candidate = self.root / filename
        if not candidate.exists():
            return candidate
        stem = candidate.stem
        suffix = candidate.suffix
        index = 2
        while True:
            numbered = self.root / f"{stem}_{index}{suffix}"
            if not numbered.exists():
                return numbered
            index += 1

    def export_document(self, source: Path, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return destination
