from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from .logging_utils import configure_logging
from .meeting_record.generation_service import MeetingRecordGenerationService
from .paths import default_workspace_root, libreoffice_path, resource_path
from .services.attachment_service import AttachmentService
from .services.generation_service import GenerationService
from .services.libreoffice_service import LibreOfficeService
from .services.project_service import ProjectService
from .services.template_service import TemplateService
from .ui.main_window import MainWindow

def main() -> int:
    package_test_argument = next(
        (
            argument.split("=", 1)[1]
            for argument in sys.argv[1:]
            if argument.startswith("--package-self-test-root=")
        ),
        "",
    )
    diagnostic_root = Path(package_test_argument).resolve() if package_test_argument else None
    if diagnostic_root is not None:
        diagnostic_root.mkdir(parents=True, exist_ok=True)
        (diagnostic_root / "self-test-started.txt").write_text("started\n", encoding="utf-8")
    app = QApplication(sys.argv)
    app.setApplicationName("村务材料管理")
    app.setOrganizationName("VillageDocs")
    app.setWindowIcon(QIcon(str(resource_path("icons", "villagedocs-icon.png"))))
    smoke_root = os.environ.get("HOUSEBOOK_SMOKE_TEST_DIR")
    package_test_root = package_test_argument or os.environ.get("HOUSEBOOK_PACKAGE_SELF_TEST_DIR")
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
            village_output = generation.generate(snapshot.id, output_format="pdf", allow_incomplete=True)
            meeting = projects.create_meeting_record()
            meeting.meeting_name = "虚构打包冒烟会议"
            meeting.content = "会议记录模块打包冒烟测试。"
            projects.repository.save_meeting_record(meeting)
            meeting_output = MeetingRecordGenerationService(projects).generate(meeting.id)
            return 0 if village_output.is_file() and meeting_output.is_file() else 2
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
            failure_root = Path(package_test_root).resolve()
            failure_root.mkdir(parents=True, exist_ok=True)
            (failure_root / "self-test-error.txt").write_text(
                traceback.format_exc(), encoding="utf-8"
            )
            return 1
        QMessageBox.critical(None, "启动失败", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
