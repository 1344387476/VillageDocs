from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from .logging_utils import configure_logging
from .paths import default_workspace_root, libreoffice_path, resource_path
from .services.attachment_service import AttachmentService
from .services.generation_service import GenerationService
from .services.libreoffice_service import LibreOfficeService
from .services.project_service import ProjectService
from .services.template_service import TemplateService
from .ui.main_window import MainWindow

def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("村务材料管理")
    app.setOrganizationName("VillageDocs")
    smoke_root = os.environ.get("HOUSEBOOK_SMOKE_TEST_DIR")
    package_test_root = os.environ.get("HOUSEBOOK_PACKAGE_SELF_TEST_DIR")
    workspace_override = package_test_root or smoke_root
    workspace = Path(workspace_override).resolve() if workspace_override else default_workspace_root()
    try:
        projects = ProjectService(workspace)
        configure_logging(projects.root / "logs")
        attachments = AttachmentService(projects)
        templates = TemplateService(resource_path("templates", "house_building"))
        converter = LibreOfficeService(libreoffice_path())
        if smoke_root and not converter.available():
            raise RuntimeError("内置 LibreOffice 不可用")
        generation = GenerationService(projects, templates, attachments, converter)
        if package_test_root:
            snapshot = projects.create_project("village_house")
            snapshot.applicant.name = "虚构测试用户"
            projects.repository.save(snapshot)
            output = generation.generate(snapshot.id, output_format="pdf", allow_incomplete=True)
            return 0 if output.is_file() else 2
        window = MainWindow(projects, attachments, generation)
        window.show()
        if smoke_root:
            window.new_project()
            app.processEvents()
            window.close()
            return 0
        return app.exec()
    except Exception as exc:
        if package_test_root:
            return 1
        QMessageBox.critical(None, "启动失败", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
