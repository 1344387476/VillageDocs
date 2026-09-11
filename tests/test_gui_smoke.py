from __future__ import annotations

import os
from pathlib import Path

import fitz

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea

from housebook.paths import libreoffice_path
from housebook.services.attachment_service import AttachmentService
from housebook.services.generation_service import GenerationService
from housebook.services.libreoffice_service import LibreOfficeService
from housebook.services.project_service import ProjectService
from housebook.services.template_service import TemplateService
from housebook.ui.main_window import DocumentWorker, MainWindow
from tests.test_real_templates import TEMPLATES


def test_main_window_starts_offscreen(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    projects = ProjectService(tmp_path / "workspace")
    attachments = AttachmentService(projects)
    generation = GenerationService(projects, TemplateService(TEMPLATES), attachments, LibreOfficeService(libreoffice_path()))
    window = MainWindow(projects, attachments, generation)
    assert window.snapshot is None
    assert window.page_stack.currentIndex() == 0
    window.enter_village_house_module()
    assert window.page_stack.currentIndex() == 1
    assert "#28A860" in window.styleSheet()
    assert not window.project_empty.isHidden()
    assert window.project_list.isHidden()
    assert not window.open_project_button.isEnabled()
    window.new_project()
    assert window.snapshot is not None
    assert window.page_stack.currentIndex() == 2
    assert window.project_empty.isHidden()
    assert window.tabs.count() == 6
    assert window.tabs.tabBar().isHidden()
    assert len(window.findChildren(QScrollArea)) >= 3
    labels = {button.text() for button in window.findChildren(QPushButton)}
    assert "生成完整材料 Word" in labels
    assert "生成完整材料 PDF" in labels
    assert "打开输出文件" in labels
    assert "删除选中材料" in labels
    bound_lines = {line.property("binding"): line for line in window.findChildren(QLineEdit)}
    assert "不要填写完整地址" in bound_lines["applicant.town"].placeholderText()
    assert "不要填写完整地址" in bound_lines["applicant.administrative_village"].placeholderText()
    assert "唯一住宅证明只取镇、村、组" in bound_lines["applicant.group_name"].placeholderText()
    assert "进入记录  →" in labels

    stale_preview = QLabel("上一次生成的材料")
    window.pdf_pages_layout.addWidget(stale_preview)
    window.step_menu.setCurrentRow(5)
    window.new_project()
    assert window.step_menu.currentRow() == 0
    assert window.tabs.currentIndex() == 0
    assert window.pdf_pages_layout.count() == 0
    assert stale_preview.parent() is None
    window.close()
    app.processEvents()


def test_meeting_record_module_requires_template_then_locks_it(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    projects = ProjectService(tmp_path / "workspace")
    attachments = AttachmentService(projects)
    generation = GenerationService(
        projects, TemplateService(TEMPLATES), attachments, LibreOfficeService(libreoffice_path())
    )
    window = MainWindow(projects, attachments, generation)

    window.enter_meeting_record_module()
    page = window.meeting_page
    assert window.page_stack.currentWidget() is page
    assert page.pages.currentIndex() == 0
    page.show_template_selection()
    assert page.pages.currentIndex() == 1
    template = page.registry.get("standard_meeting_record", 1)
    page.create_record(template)
    assert page.pages.currentIndex() == 2
    assert page.snapshot is not None
    assert page.snapshot.template_id == "standard_meeting_record"
    assert "模板已锁定" in page.editor_template.text()
    assert projects.repository.list_projects(material_type="village_house") == []
    assert len(projects.repository.list_meeting_records()) == 1

    window.close()
    app.processEvents()


def test_project_list_can_delete_selected_material(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    projects = ProjectService(tmp_path / "workspace")
    project = projects.create_project()
    project.applicant.name = "待删除测试材料"
    projects.repository.save(project)
    attachments = AttachmentService(projects)
    generation = GenerationService(projects, TemplateService(TEMPLATES), attachments, LibreOfficeService(libreoffice_path()))
    window = MainWindow(projects, attachments, generation)
    window.enter_village_house_module()
    window.project_list.item(0).setSelected(True)

    deleted: list[str] = []

    def delete_one(project_id: str) -> None:
        deleted.append(project_id)
        projects.repository.delete_project_record(project_id)

    monkeypatch.setattr(projects, "delete_project_to_recycle_bin", delete_one)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes)

    window.delete_selected_project()

    assert deleted == [project.id]
    assert projects.repository.list_projects() == []
    assert window.project_list.count() == 0
    window.close()
    app.processEvents()


def test_history_word_preview_reuses_cached_pdf(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    projects = ProjectService(tmp_path / "workspace")
    project = projects.create_project()
    word_output = projects.root / "上次生成.docx"
    word_output.write_bytes(b"cached word output")
    preview_dir = projects.project_dir(project.id) / "temp" / f"preview-{word_output.stem}"
    preview_dir.mkdir(parents=True, exist_ok=True)
    cached_preview = preview_dir / f"{word_output.stem}.pdf"
    document = fitz.open()
    document.new_page()
    document.save(cached_preview)
    document.close()

    class ConverterThatMustNotRun:
        def to_pdf(self, _source: Path, _output_dir: Path) -> Path:
            raise AssertionError("打开历史记录时不应重新转换已有预览")

    class CachedGeneration:
        converter = ConverterThatMustNotRun()

    completed: list[tuple[str, str, list[bytes]]] = []
    failures: list[str] = []
    worker = DocumentWorker(
        CachedGeneration(),  # type: ignore[arg-type]
        projects,
        project_id=project.id,
        preview_source=word_output,
    )
    worker.completed.connect(lambda output, preview, pages: completed.append((output, preview, pages)))
    worker.failed.connect(failures.append)

    worker.run()

    assert failures == []
    assert len(completed) == 1
    assert completed[0][0] == str(word_output)
    assert completed[0][1] == str(cached_preview)
    assert len(completed[0][2]) == 1
