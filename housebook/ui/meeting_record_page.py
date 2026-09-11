from __future__ import annotations

from pathlib import Path

import fitz
from PySide6.QtCore import QObject, QSize, QThread, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices, QImage, QPageLayout, QPageSize, QPainter, QPixmap
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..meeting_record.generation_service import MeetingRecordGenerationService
from ..meeting_record.template_config import MeetingTemplate, MeetingTemplateRegistry
from ..models import MeetingRecordSnapshot
from ..services.project_service import ProjectService


class MeetingPdfWorker(QObject):
    completed = Signal(str, object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        generation: MeetingRecordGenerationService,
        project_id: str,
        preview_source: Path | None = None,
    ) -> None:
        super().__init__()
        self.generation = generation
        self.project_id = project_id
        self.preview_source = preview_source

    @Slot()
    def run(self) -> None:
        try:
            output = self.preview_source or self.generation.generate(self.project_id)
            pages: list[bytes] = []
            with fitz.open(output) as document:
                for page in document:
                    pages.append(
                        page.get_pixmap(matrix=fitz.Matrix(1.15, 1.15), alpha=False).tobytes("png")
                    )
            self.completed.emit(str(output), pages)
        except Exception as exc:
            self.failed.emit(str(exc).strip() or "会议记录生成失败")
        finally:
            self.finished.emit()


class MeetingRecordModulePage(QWidget):
    back_requested = Signal()

    def __init__(
        self,
        projects: ProjectService,
        generation: MeetingRecordGenerationService | None = None,
        registry: MeetingTemplateRegistry | None = None,
    ) -> None:
        super().__init__()
        self.setProperty("page", True)
        self.projects = projects
        self.registry = registry or MeetingTemplateRegistry()
        self.generation = generation or MeetingRecordGenerationService(projects, self.registry)
        self.snapshot: MeetingRecordSnapshot | None = None
        self._loading = False
        self._output_path: Path | None = None
        self._pdf_document: fitz.Document | None = None
        self._worker_thread: QThread | None = None
        self._worker: MeetingPdfWorker | None = None
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(650)
        self._save_timer.timeout.connect(self.save_current)
        self._build_ui()

    @staticmethod
    def _label(text: str, role: str, *, word_wrap: bool = False) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", role)
        label.setWordWrap(word_wrap)
        return label

    @staticmethod
    def _button(text: str, role: str = "secondary") -> QPushButton:
        button = QPushButton(text)
        button.setProperty("role", role)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    @staticmethod
    def _card(role: str = "card") -> QFrame:
        card = QFrame()
        card.setProperty("role", role)
        return card

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_list_page())
        self.pages.addWidget(self._build_template_page())
        self.pages.addWidget(self._build_editor_page())
        layout.addWidget(self.pages)

    def _build_list_page(self) -> QWidget:
        page = QWidget()
        page.setProperty("page", True)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 28, 40, 36)
        layout.setSpacing(18)
        header = QHBoxLayout()
        back = self._button("←  材料类型", "ghost")
        back.clicked.connect(self._back_home)
        heading = QVBoxLayout()
        heading.addWidget(self._label("会议记录", "pageTitle"))
        heading.addWidget(self._label("管理会议记录，双击任意记录即可继续填写。", "secondary"))
        new_button = self._button("＋  新建会议记录", "primary")
        new_button.clicked.connect(self.show_template_selection)
        header.addWidget(back)
        header.addSpacing(8)
        header.addLayout(heading)
        header.addStretch(1)
        header.addWidget(new_button)

        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setProperty("role", "search")
        self.search.setPlaceholderText("搜索会议名称、时间或主题…")
        self.search.setMaximumWidth(460)
        self.search.textChanged.connect(self.refresh_records)
        self.record_count_label = self._label("0 条记录", "tertiary")
        toolbar.addWidget(self.search, 1)
        toolbar.addStretch(1)
        toolbar.addWidget(self.record_count_label)

        records_card = self._card()
        records_layout = QVBoxLayout(records_card)
        records_layout.setContentsMargins(0, 0, 0, 14)
        self.record_list = QListWidget()
        self.record_list.setProperty("role", "records")
        self.record_list.itemDoubleClicked.connect(lambda _item: self.open_selected_record())
        self.record_list.itemSelectionChanged.connect(self._update_record_actions)
        records_layout.addWidget(self.record_list, 1)
        self.empty_panel = QWidget()
        empty = QVBoxLayout(self.empty_panel)
        empty.setContentsMargins(32, 72, 32, 72)
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_title = self._label("还没有会议记录", "emptyTitle")
        self.empty_text = self._label("选择模板后即可录入第一份会议记录。", "emptyText")
        first = self._button("新建第一份会议记录", "primary")
        first.clicked.connect(self.show_template_selection)
        empty.addWidget(self.empty_title, 0, Qt.AlignmentFlag.AlignHCenter)
        empty.addWidget(self.empty_text, 0, Qt.AlignmentFlag.AlignHCenter)
        empty.addSpacing(8)
        empty.addWidget(first, 0, Qt.AlignmentFlag.AlignHCenter)
        records_layout.addWidget(self.empty_panel, 1)
        actions = QHBoxLayout()
        actions.setContentsMargins(14, 14, 14, 0)
        actions.addStretch(1)
        self.delete_record_button = self._button("删除选中记录", "danger")
        self.delete_record_button.clicked.connect(self.delete_selected_record)
        self.open_record_button = self._button("打开选中记录")
        self.open_record_button.clicked.connect(self.open_selected_record)
        actions.addWidget(self.delete_record_button)
        actions.addWidget(self.open_record_button)
        records_layout.addLayout(actions)

        layout.addLayout(header)
        layout.addLayout(toolbar)
        layout.addWidget(records_card, 1)
        return page

    def _build_template_page(self) -> QWidget:
        page = QWidget()
        page.setProperty("page", True)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 30, 48, 42)
        layout.setSpacing(20)
        header = QHBoxLayout()
        back = self._button("←  会议记录", "ghost")
        back.clicked.connect(self.show_record_list)
        title = QVBoxLayout()
        title.addWidget(self._label("选择会议模板", "pageTitle"))
        title.addWidget(self._label("模板在记录创建后锁定；需要其他模板时请新建记录。", "secondary"))
        header.addWidget(back)
        header.addSpacing(8)
        header.addLayout(title)
        header.addStretch(1)
        layout.addLayout(header)

        self.template_cards = QHBoxLayout()
        self.template_cards.setSpacing(18)
        for template in self.registry.templates():
            self.template_cards.addWidget(self._template_card(template), 0, Qt.AlignmentFlag.AlignTop)
        self.template_cards.addStretch(1)
        layout.addLayout(self.template_cards)
        layout.addStretch(1)
        return page

    def _template_card(self, template: MeetingTemplate) -> QFrame:
        card = self._card("featureCard")
        card.setFixedWidth(310)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        preview = QLabel()
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setMinimumHeight(235)
        preview.setProperty("role", "documentPage")
        if template.thumbnail.is_file():
            pixmap = QPixmap(str(template.thumbnail))
            preview.setPixmap(
                pixmap.scaled(178, 252, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
        layout.addWidget(preview)
        layout.addWidget(self._label(template.name, "cardTitle"))
        layout.addWidget(self._label(template.description, "secondary", word_wrap=True))
        layout.addWidget(self._label(f"模板版本 v{template.version}", "tertiary"))
        use = self._button("使用此模板", "primary")
        use.clicked.connect(lambda _checked=False, item=template: self.create_record(item))
        layout.addWidget(use)
        return card

    def _build_editor_page(self) -> QWidget:
        page = QWidget()
        page.setProperty("page", True)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(20, 16, 20, 20)
        outer.setSpacing(12)
        header = QHBoxLayout()
        back = self._button("←  会议记录列表", "ghost")
        back.clicked.connect(self.back_to_list)
        titles = QVBoxLayout()
        self.editor_title = self._label("未命名会议", "sectionTitle")
        self.editor_template = self._label("标准会议记录 · 模板已锁定", "tertiary")
        titles.addWidget(self.editor_title)
        titles.addWidget(self.editor_template)
        delete = self._button("删除当前记录", "danger")
        delete.clicked.connect(self.delete_current_record)
        header.addWidget(back)
        header.addSpacing(6)
        header.addLayout(titles)
        header.addStretch(1)
        header.addWidget(delete)

        progress = QHBoxLayout()
        self.progress_label = self._label("信息会自动保存", "success")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setMaximumWidth(240)
        self.progress_bar.hide()
        progress.addWidget(self.progress_label)
        progress.addStretch(1)
        progress.addWidget(self.progress_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        navigation = self._card()
        nav_layout = QVBoxLayout(navigation)
        nav_layout.setContentsMargins(14, 18, 14, 16)
        nav_layout.addWidget(self._label("录入流程", "cardTitle"))
        nav_layout.addWidget(self._label("所有字段均可留空", "tertiary"))
        self.step_menu = QListWidget()
        self.step_menu.setProperty("role", "steps")
        self.step_menu.addItems(["01   会议信息", "02   会议内容", "03   生成预览"])
        self.step_menu.currentRowChanged.connect(self._set_step)
        nav_layout.addWidget(self.step_menu, 1)
        navigation.setMinimumWidth(210)
        navigation.setMaximumWidth(238)

        content = self._card()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 24, 28, 24)
        self.section_title = self._label("会议信息", "sectionTitle")
        self.section_description = self._label("填写会议基本信息和参会人员。", "secondary")
        self.editor_pages = QStackedWidget()
        self.editor_pages.addWidget(self._build_information_form())
        self.editor_pages.addWidget(self._build_content_form())
        self.editor_pages.addWidget(self._build_preview_page())
        content_layout.addWidget(self.section_title)
        content_layout.addWidget(self.section_description)
        content_layout.addSpacing(8)
        content_layout.addWidget(self.editor_pages, 1)

        splitter.addWidget(navigation)
        splitter.addWidget(content)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 1080])
        outer.addLayout(header)
        outer.addLayout(progress)
        outer.addWidget(splitter, 1)
        self.step_menu.setCurrentRow(0)
        return page

    def _form_scroll(self, form: QFormLayout) -> QScrollArea:
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        body = QWidget()
        body.setLayout(form)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        return scroll

    def _line(self, key: str, placeholder: str = "") -> QLineEdit:
        widget = QLineEdit()
        widget.setProperty("meetingBinding", key)
        widget.setPlaceholderText(placeholder)
        widget.textChanged.connect(self.schedule_save)
        return widget

    def _plain(self, key: str, placeholder: str, minimum_height: int) -> QPlainTextEdit:
        widget = QPlainTextEdit()
        widget.setProperty("meetingBinding", key)
        widget.setPlaceholderText(placeholder)
        widget.setMinimumHeight(minimum_height)
        widget.textChanged.connect(self.schedule_save)
        return widget

    def _optional_count(self, key: str) -> QSpinBox:
        widget = QSpinBox()
        widget.setProperty("meetingBinding", key)
        widget.setRange(-1, 999999)
        widget.setSpecialValueText("")
        widget.setValue(-1)
        widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        widget.valueChanged.connect(self.schedule_save)
        return widget

    def _build_information_form(self) -> QScrollArea:
        form = QFormLayout()
        form.addRow("会议名称", self._line("meeting_name", "例如：村民代表会议"))
        form.addRow("时间", self._line("meeting_time", "自由填写，例如：2026年9月11日上午9时"))
        form.addRow("地点", self._line("location", "例如：村会议室"))
        counts = QHBoxLayout()
        self.expected_count = self._optional_count("expected_count")
        self.actual_count = self._optional_count("actual_count")
        counts.addWidget(self._label("应到", "secondary"))
        counts.addWidget(self.expected_count)
        counts.addSpacing(20)
        counts.addWidget(self._label("实到", "secondary"))
        counts.addWidget(self.actual_count)
        counts.addStretch(1)
        form.addRow("人数", counts)
        form.addRow("参加人员", self._plain("participants", "可换行填写，模板最多六行", 118))
        form.addRow("列席人员", self._plain("observers", "可留空", 70))
        form.addRow("主持人", self._line("chairperson"))
        form.addRow("记录人", self._line("recorder"))
        return self._form_scroll(form)

    def _build_content_form(self) -> QScrollArea:
        form = QFormLayout()
        form.addRow("主题", self._plain("topic", "可换行填写，模板最多两行", 100))
        form.addRow(
            "主要内容",
            self._plain("content", "保留换行和空行；第一页写满后自动增加续页", 390),
        )
        return self._form_scroll(form)

    def _build_preview_page(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self.pdf_scroll = QScrollArea()
        self.pdf_scroll.setWidgetResizable(True)
        self.pdf_pages = QWidget()
        self.pdf_pages_layout = QVBoxLayout(self.pdf_pages)
        self.pdf_pages_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.pdf_scroll.setWidget(self.pdf_pages)
        buttons = QHBoxLayout()
        self.generate_button = self._button("生成 PDF 预览", "primary")
        self.generate_button.clicked.connect(self.generate_pdf)
        self.open_button = self._button("打开输出文件")
        self.open_button.clicked.connect(self.open_output)
        self.save_as_button = self._button("另存为")
        self.save_as_button.clicked.connect(self.save_output_as)
        self.print_button = self._button("打印")
        self.print_button.clicked.connect(self.print_pdf)
        buttons.addWidget(self.generate_button)
        buttons.addStretch(1)
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.save_as_button)
        buttons.addWidget(self.print_button)
        layout.addWidget(self.pdf_scroll, 1)
        layout.addLayout(buttons)
        self._update_output_actions()
        return panel

    def enter(self) -> None:
        self.save_current()
        self.snapshot = None
        self.refresh_records()
        self.pages.setCurrentIndex(0)

    def _back_home(self) -> None:
        if self._worker_thread is not None:
            QMessageBox.information(self, "正在处理", "请等待当前生成或预览任务完成。")
            return
        self.save_current()
        self.snapshot = None
        self.back_requested.emit()

    def show_record_list(self) -> None:
        self.refresh_records()
        self.pages.setCurrentIndex(0)

    def show_template_selection(self) -> None:
        self.save_current()
        self.snapshot = None
        self.pages.setCurrentIndex(1)

    def create_record(self, template: MeetingTemplate) -> None:
        record = self.projects.create_meeting_record(template.template_id, template.version)
        self.load_record(record)

    def refresh_records(self) -> None:
        records = self.projects.repository.list_meeting_records(self.search.text().strip())
        self.record_list.clear()
        for record in records:
            try:
                template_name = self.registry.get(record.template_id, record.template_version).name
            except KeyError:
                template_name = f"未知模板 v{record.template_version}"
            item = QListWidgetItem(
                f"{record.meeting_name or '未命名会议'}    ·    {record.meeting_time or '时间未填写'}\n"
                f"主题：{record.topic or '未填写'}    ·    {template_name}    ·    更新：{record.updated_at.replace('T', ' ')}"
            )
            item.setData(Qt.ItemDataRole.UserRole, record.id)
            item.setSizeHint(QSize(0, 76))
            item.setToolTip("双击继续填写")
            self.record_list.addItem(item)
        self.record_count_label.setText(f"{len(records)} 条记录")
        is_empty = not records
        self.empty_panel.setVisible(is_empty)
        self.record_list.setVisible(not is_empty)
        if is_empty and self.search.text().strip():
            self.empty_title.setText("没有找到匹配记录")
            self.empty_text.setText("请检查会议名称、时间或主题，或清空搜索后再试。")
        else:
            self.empty_title.setText("还没有会议记录")
            self.empty_text.setText("选择模板后即可录入第一份会议记录。")
        self._update_record_actions()

    def _update_record_actions(self) -> None:
        enabled = bool(self.record_list.selectedItems())
        self.open_record_button.setEnabled(enabled)
        self.delete_record_button.setEnabled(enabled)

    def open_selected_record(self) -> None:
        selected = self.record_list.selectedItems()
        if selected:
            self.load_record(self.projects.repository.load_meeting_record(selected[0].data(Qt.ItemDataRole.UserRole)))

    def load_record(self, snapshot: MeetingRecordSnapshot) -> None:
        self._loading = True
        self.snapshot = snapshot
        self._clear_preview()
        template = self.registry.get(snapshot.template_id, snapshot.template_version)
        self.editor_title.setText(snapshot.meeting_name or "未命名会议")
        self.editor_template.setText(f"{template.name} v{template.version} · 模板已锁定")
        for widget in self._field_widgets():
            key = widget.property("meetingBinding")
            if not key:
                continue
            value = getattr(snapshot, key)
            if isinstance(widget, QLineEdit):
                widget.setText(value or "")
            elif isinstance(widget, QPlainTextEdit):
                widget.setPlainText(value or "")
            elif isinstance(widget, QSpinBox):
                widget.setValue(-1 if value is None else int(value))
        self.step_menu.setCurrentRow(0)
        self.pages.setCurrentIndex(2)
        self._loading = False
        if snapshot.output_pdf_path:
            output = self.projects.root / snapshot.output_pdf_path
            if output.is_file():
                self.step_menu.setCurrentRow(2)
                QTimer.singleShot(0, lambda path=output: self.start_preview(path))

    def schedule_save(self) -> None:
        if not self._loading and self.snapshot is not None:
            self.progress_label.setText("正在保存…")
            self._save_timer.start()

    def save_current(self) -> None:
        if self._loading or self.snapshot is None:
            return
        for widget in self._field_widgets():
            key = widget.property("meetingBinding")
            if not key:
                continue
            if isinstance(widget, QLineEdit):
                value = widget.text()
            elif isinstance(widget, QPlainTextEdit):
                value = widget.toPlainText()
            else:
                value = None if widget.value() < 0 else widget.value()
            setattr(self.snapshot, key, value)
        self.projects.repository.save_meeting_record(self.snapshot)
        self.editor_title.setText(self.snapshot.meeting_name or "未命名会议")
        self.progress_label.setText("已自动保存")

    def _field_widgets(self) -> list[QLineEdit | QPlainTextEdit | QSpinBox]:
        return [
            *self.findChildren(QLineEdit),
            *self.findChildren(QPlainTextEdit),
            *self.findChildren(QSpinBox),
        ]

    def back_to_list(self) -> None:
        if self._worker_thread is not None:
            QMessageBox.information(self, "正在处理", "请等待当前生成或预览任务完成。")
            return
        self.save_current()
        self.snapshot = None
        self._clear_preview()
        self.show_record_list()

    def _set_step(self, row: int) -> None:
        if row < 0:
            return
        meta = (
            ("会议信息", "填写会议基本信息和参会人员。"),
            ("会议内容", "填写会议主题和主要内容，换行会原样保留。"),
            ("生成预览", "生成最终 PDF 后可另存为或打印。"),
        )
        self.section_title.setText(meta[row][0])
        self.section_description.setText(meta[row][1])
        self.editor_pages.setCurrentIndex(row)

    def generate_pdf(self) -> None:
        if self.snapshot is None or self._worker_thread is not None:
            return
        self.save_current()
        self._start_worker()

    def start_preview(self, path: Path) -> None:
        if self.snapshot is None or self._worker_thread is not None:
            return
        self._start_worker(path)

    def _start_worker(self, preview_source: Path | None = None) -> None:
        assert self.snapshot is not None
        self._set_busy(True, "正在加载预览…" if preview_source else "正在生成会议记录…")
        thread = QThread(self)
        worker = MeetingPdfWorker(self.generation, self.snapshot.id, preview_source)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._worker_completed)
        worker.failed.connect(self._worker_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._worker_finished)
        self._worker_thread = thread
        self._worker = worker
        thread.start()

    @Slot(str, object)
    def _worker_completed(self, output: str, page_images: list[bytes]) -> None:
        path = Path(output)
        self._output_path = path
        self._clear_preview(reset_output=False)
        self._pdf_document = fitz.open(path)
        for page_number, payload in enumerate(page_images):
            image = QImage()
            image.loadFromData(payload, "PNG")
            label = QLabel()
            label.setPixmap(QPixmap.fromImage(image))
            label.setToolTip(f"第 {page_number + 1} 页")
            label.setProperty("role", "documentPage")
            self.pdf_pages_layout.addWidget(label)
        if self.snapshot:
            self.snapshot = self.projects.repository.load_meeting_record(self.snapshot.id)
        self.step_menu.setCurrentRow(2)
        self.progress_label.setText("PDF 已生成")
        self._update_output_actions()

    @Slot(str)
    def _worker_failed(self, message: str) -> None:
        QMessageBox.critical(self, "生成失败", message)
        self.progress_label.setText("生成失败，请检查提示")

    @Slot()
    def _worker_finished(self) -> None:
        thread = self._worker_thread
        self._worker = None
        self._worker_thread = None
        self._set_busy(False)
        if thread is not None:
            thread.deleteLater()

    def _set_busy(self, busy: bool, text: str = "") -> None:
        self.progress_bar.setVisible(busy)
        self.generate_button.setEnabled(not busy)
        if text:
            self.progress_label.setText(text)
        self._update_output_actions()

    def _update_output_actions(self) -> None:
        available = bool(self._output_path and self._output_path.is_file())
        busy = self._worker_thread is not None
        for button in (self.open_button, self.save_as_button, self.print_button):
            button.setEnabled(available and not busy)

    def _clear_preview(self, *, reset_output: bool = True) -> None:
        if self._pdf_document is not None:
            self._pdf_document.close()
            self._pdf_document = None
        while self.pdf_pages_layout.count():
            item = self.pdf_pages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if reset_output:
            self._output_path = None
        self._update_output_actions()

    def open_output(self) -> None:
        if self._output_path and self._output_path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._output_path)))

    def save_output_as(self) -> None:
        if not self._output_path or not self._output_path.is_file():
            return
        destination, _ = QFileDialog.getSaveFileName(
            self, "另存会议记录 PDF", self._output_path.name, "PDF 文件 (*.pdf)"
        )
        if destination:
            self.projects.export_document(self._output_path, Path(destination))

    def print_pdf(self) -> None:
        if self._pdf_document is None or self._pdf_document.page_count < 1:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        printer.setPageOrientation(QPageLayout.Orientation.Portrait)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return
        painter = QPainter(printer)
        try:
            dpi = max(300, min(printer.resolution(), 600))
            for page_number in range(self._pdf_document.page_count):
                if page_number:
                    printer.newPage()
                viewport = painter.viewport()
                page = self._pdf_document.load_page(page_number)
                pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), alpha=False)
                image = QImage(
                    pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888
                ).copy()
                scaled = image.scaled(
                    viewport.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                x = viewport.x() + (viewport.width() - scaled.width()) // 2
                y = viewport.y() + (viewport.height() - scaled.height()) // 2
                painter.drawImage(x, y, scaled)
        finally:
            painter.end()

    def delete_selected_record(self) -> None:
        selected = self.record_list.selectedItems()
        if not selected:
            return
        record = self.projects.repository.load_meeting_record(
            selected[0].data(Qt.ItemDataRole.UserRole)
        )
        if self._confirm_delete(record):
            self.refresh_records()

    def delete_current_record(self) -> None:
        if self.snapshot and self._confirm_delete(self.snapshot):
            self.snapshot = None
            self._clear_preview()
            self.show_record_list()

    def _confirm_delete(self, record: MeetingRecordSnapshot) -> bool:
        answer = QMessageBox.warning(
            self,
            "确认删除",
            f"确认将“{record.meeting_name or '未命名会议'}”及其输出移入 Windows 回收站？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        self.projects.delete_project_to_recycle_bin(record.id)
        return True

    def can_close(self) -> bool:
        if self._worker_thread is not None:
            QMessageBox.information(self, "正在处理", "请等待会议记录生成或预览完成后再关闭。")
            return False
        self.save_current()
        return True
