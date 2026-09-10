from __future__ import annotations

import os
from dataclasses import fields
from pathlib import Path

import fitz

from PySide6.QtCore import QObject, QThread, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices, QImage, QPainter, QPixmap
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QProgressBar, QScrollArea, QSpinBox, QSplitter, QStackedWidget, QStatusBar, QTabWidget,
    QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..constants import MATERIALS, MATERIAL_BY_CODE
from ..models import Applicant, ExistingHouse, FamilyMember, ProjectSnapshot, ProposedHouse, PublicNotice
from ..validation import validate_snapshot
from ..services.attachment_service import AttachmentService
from ..services.generation_service import GenerationService
from ..services.project_service import ProjectService


class DocumentWorker(QObject):
    progress = Signal(str)
    completed = Signal(str, str, object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        generation: GenerationService,
        projects: ProjectService,
        *,
        project_id: str = "",
        output_format: str = "pdf",
        allow_incomplete: bool = False,
        preview_source: Path | None = None,
    ) -> None:
        super().__init__()
        self.generation = generation
        self.projects = projects
        self.project_id = project_id
        self.output_format = output_format
        self.allow_incomplete = allow_incomplete
        self.preview_source = preview_source

    @Slot()
    def run(self) -> None:
        try:
            generated_now = self.preview_source is None
            if generated_now:
                self.progress.emit("正在准备模板并合并材料…")
                output = self.generation.generate(
                    self.project_id,
                    output_format=self.output_format,
                    allow_incomplete=self.allow_incomplete,
                )
            else:
                output = self.preview_source
            preview = output
            if output.suffix.lower() == ".docx":
                preview_dir = self.projects.project_dir(self.project_id) / "temp" / f"preview-{output.stem}"
                cached_preview = preview_dir / f"{output.stem}.pdf"
                cache_is_current = (
                    cached_preview.exists()
                    and cached_preview.stat().st_mtime >= output.stat().st_mtime
                )
                if generated_now or not cache_is_current:
                    self.progress.emit("正在准备 Word 预览…")
                    preview = self.generation.converter.to_pdf(output, preview_dir)
                else:
                    self.progress.emit("正在加载上次生成的预览…")
                    preview = cached_preview
            else:
                self.progress.emit("正在加载上次生成的预览…" if not generated_now else "正在加载预览…")
            pages: list[bytes] = []
            with fitz.open(preview) as document:
                for page in document:
                    pages.append(page.get_pixmap(matrix=fitz.Matrix(1.15, 1.15), alpha=False).tobytes("png"))
            self.completed.emit(str(output), str(preview), pages)
        except Exception as exc:
            message = str(exc).strip() or "生成过程中发生未知错误"
            if "docxcompose" in message or "custom.xml" in message:
                message = "安装组件不完整，请重新安装村务材料管理 1.1"
            self.failed.emit(message)
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self, projects: ProjectService, attachments: AttachmentService, generation: GenerationService) -> None:
        super().__init__()
        self.projects = projects
        self.attachments = attachments
        self.generation = generation
        self.snapshot: ProjectSnapshot | None = None
        self._loading = False
        self._output_path: Path | None = None
        self._preview_pdf_path: Path | None = None
        self._pdf_document: fitz.Document | None = None
        self._worker_thread: QThread | None = None
        self._worker: DocumentWorker | None = None
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(650)
        self._save_timer.timeout.connect(self.save_current)
        self.setWindowTitle("村务材料管理 1.1")
        self.resize(1320, 850)
        self.setStatusBar(QStatusBar())
        self._build_ui()
        self.refresh_projects()

    def _build_ui(self) -> None:
        self.page_stack = QStackedWidget()
        self.page_stack.addWidget(self._build_home_page())
        self.page_stack.addWidget(self._build_module_page())
        self.page_stack.addWidget(self._build_editor_page())
        self.setCentralWidget(self.page_stack)
        self.page_stack.setCurrentIndex(0)

    def _build_home_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(80, 60, 80, 60)
        title = QLabel("请选择材料类型")
        title.setStyleSheet("font-size:30px;font-weight:700")
        subtitle = QLabel("进入对应模块后，可以新建或继续办理已有材料。")
        subtitle.setStyleSheet("font-size:15px;color:#666;margin-bottom:24px")
        card = QPushButton("村建材料\n\n村民建房报备材料自动填写、附件整理与成册")
        card.setMinimumSize(430, 210)
        card.setMaximumWidth(560)
        card.setStyleSheet(
            "QPushButton{text-align:left;padding:32px;font-size:20px;font-weight:600;"
            "background:white;border:2px solid #d8e2f0;border-radius:16px;}"
            "QPushButton:hover{border-color:#2878d0;background:#f4f9ff;}"
        )
        card.clicked.connect(self.enter_village_house_module)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(card, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        return page

    def _build_module_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(44, 28, 44, 36)
        header = QHBoxLayout()
        back = QPushButton("← 返回材料类型")
        back.clicked.connect(self.back_to_home)
        title = QLabel("村建材料")
        title.setStyleSheet("font-size:25px;font-weight:700")
        new_button = QPushButton("＋ 新建材料")
        new_button.setStyleSheet("padding:10px 22px;font-weight:600")
        new_button.clicked.connect(self.new_project)
        header.addWidget(back)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(new_button)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索申请人")
        self.search.setMaximumWidth(420)
        self.search.textChanged.connect(self.refresh_projects)
        self.project_list = QListWidget()
        self.project_list.setSpacing(5)
        self.project_list.itemDoubleClicked.connect(lambda _item: self.open_selected_project())
        open_button = QPushButton("打开选中材料")
        open_button.clicked.connect(self.open_selected_project)
        delete_button = QPushButton("删除选中材料")
        delete_button.clicked.connect(self.delete_selected_project)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(delete_button)
        actions.addWidget(open_button)
        layout.addLayout(header)
        layout.addSpacing(18)
        layout.addWidget(self.search)
        layout.addWidget(self.project_list, 1)
        layout.addLayout(actions)
        return page

    def _build_editor_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(22, 18, 22, 18)
        header = QHBoxLayout()
        back = QPushButton("← 返回材料列表")
        back.clicked.connect(self.back_to_module)
        self.editor_title = QLabel("未命名材料")
        self.editor_title.setStyleSheet("font-size:21px;font-weight:650")
        delete_button = QPushButton("删除当前材料")
        delete_button.clicked.connect(self.delete_current_project)
        header.addWidget(back)
        header.addWidget(self.editor_title)
        header.addStretch(1)
        header.addWidget(delete_button)
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("color:#245d9c")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setMaximumWidth(240)
        self.progress_bar.hide()
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress_label)
        progress_row.addStretch(1)
        progress_row.addWidget(self.progress_bar)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.step_menu = QListWidget()
        self.step_menu.addItems(["申请人信息", "家庭成员", "宅基地及住房", "公示信息", "材料清单", "生成预览"])
        self.step_menu.setFixedWidth(190)
        self.step_menu.currentRowChanged.connect(lambda row: self.tabs.setCurrentIndex(max(0, row)))
        splitter.addWidget(self.step_menu)
        splitter.addWidget(self._build_editor())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([190, 1050])
        outer.addLayout(header)
        outer.addLayout(progress_row)
        outer.addWidget(splitter, 1)
        self.step_menu.setCurrentRow(0)
        return page

    def _build_sidebar(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        title = QLabel("村民建房材料")
        title.setStyleSheet("font-size:20px;font-weight:600;padding:8px 0")
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索申请人")
        self.search.textChanged.connect(self.refresh_projects)
        self.project_list = QListWidget()
        self.project_list.itemSelectionChanged.connect(self.open_selected_project)
        new_button = QPushButton("新建材料")
        new_button.clicked.connect(self.new_project)
        delete_button = QPushButton("删除当前项目")
        delete_button.clicked.connect(self.delete_current_project)
        layout.addWidget(title)
        layout.addWidget(self.search)
        layout.addWidget(self.project_list, 1)
        layout.addWidget(new_button)
        layout.addWidget(delete_button)
        return panel

    def _build_editor(self) -> QWidget:
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_applicant_tab(), "申请人信息")
        self.tabs.addTab(self._build_family_tab(), "家庭成员")
        self.tabs.addTab(self._build_house_tab(), "宅基地及住房")
        self.tabs.addTab(self._build_notice_tab(), "公示信息")
        self.tabs.addTab(self._build_material_tab(), "材料清单")
        self.tabs.addTab(self._build_preview_tab(), "成册预览")
        self.tabs.tabBar().hide()
        return self.tabs

    def _line(self, key: str, placeholder: str = "") -> QLineEdit:
        widget = QLineEdit()
        if placeholder:
            widget.setPlaceholderText(placeholder)
        widget.setProperty("binding", key)
        widget.textChanged.connect(self.schedule_save)
        return widget

    def _spin(self, key: str, maximum: int = 200) -> QSpinBox:
        widget = QSpinBox()
        widget.setRange(0, maximum)
        widget.setSpecialValueText("")
        widget.setProperty("binding", key)
        widget.valueChanged.connect(self.schedule_save)
        return widget

    def _double(self, key: str) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(0, 1_000_000)
        widget.setDecimals(2)
        widget.setSpecialValueText("")
        widget.setProperty("binding", key)
        widget.valueChanged.connect(self.schedule_save)
        return widget

    def _combo(self, key: str, options: list[str]) -> QComboBox:
        widget = QComboBox()
        widget.addItems([""] + options)
        widget.setProperty("binding", key)
        widget.currentTextChanged.connect(self.schedule_save)
        return widget

    def _form_tab(self) -> tuple[QWidget, QFormLayout]:
        panel = QWidget()
        form = QFormLayout(panel)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(12)
        return panel, form

    def _build_applicant_tab(self) -> QWidget:
        panel, form = self._form_tab()
        form.addRow("姓名 *", self._line("applicant.name"))
        form.addRow("性别", self._combo("applicant.gender", ["男", "女"]))
        form.addRow("年龄", self._spin("applicant.age"))
        form.addRow("身份证号 *", self._line("applicant.id_number"))
        form.addRow("联系电话", self._line("applicant.phone"))
        form.addRow("户口所在地", self._line("applicant.household_location"))
        form.addRow("乡镇/街道（只填名称，含后缀）", self._line("applicant.town", "例如：戴南镇；不要填写完整地址"))
        form.addRow("行政村/社区（只填名称，含后缀）", self._line("applicant.administrative_village", "例如：梓辛村；不要填写完整地址"))
        form.addRow("自然村（含后缀）", self._line("applicant.natural_village"))
        form.addRow("组别（不含“组”）", self._line("applicant.group_name", "例如：一；唯一住宅证明只取镇、村、组"))
        form.addRow("家庭人口 *", self._spin("applicant.household_population", 30))
        return panel

    def _build_family_tab(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        note = QLabel("申请表母版可打印四名家庭成员；超出的成员会保存，但不会写入该母版。")
        note.setStyleSheet("color:#8a5a00;background:#fff7df;padding:8px")
        self.family_table = QTableWidget(4, 5)
        self.family_table.setHorizontalHeaderLabels(["姓名", "年龄", "与户主关系", "身份证号", "户口所在地"])
        self.family_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.family_table.itemChanged.connect(self.schedule_save)
        buttons = QHBoxLayout()
        add_row = QPushButton("添加家庭成员")
        add_row.clicked.connect(lambda: self.family_table.insertRow(self.family_table.rowCount()))
        remove_row = QPushButton("移除选中成员")
        remove_row.clicked.connect(self.remove_family_row)
        buttons.addWidget(add_row)
        buttons.addWidget(remove_row)
        buttons.addStretch(1)
        layout.addWidget(note)
        layout.addWidget(self.family_table)
        layout.addLayout(buttons)
        return panel

    def _build_house_tab(self) -> QWidget:
        panel, form = self._form_tab()
        form.addRow("现宅基地面积（㎡）", self._double("existing_house.homestead_area"))
        form.addRow("现住房建筑面积（㎡）", self._double("existing_house.building_area"))
        form.addRow("权属证书号", self._line("existing_house.ownership_certificate_no"))
        form.addRow("现宅基地处置方式", self._line("existing_house.disposal_type"))
        form.addRow("保留面积（㎡）", self._double("existing_house.disposal_area"))
        form.addRow("建房类型", self._combo("house.build_type", ["原址翻建", "改扩建", "异址新建"]))
        form.addRow("申请原因", self._line("house.application_reason"))
        form.addRow("拟建地址 *", self._line("house.address"))
        form.addRow("拟宅基地面积（㎡）", self._double("house.homestead_area"))
        form.addRow("房基占地面积（㎡）", self._double("house.footprint_area"))
        form.addRow("建筑面积（㎡）", self._double("house.building_area"))
        form.addRow("长度（米）", self._double("house.length"))
        form.addRow("宽度（米）", self._double("house.width"))
        form.addRow("层数", self._spin("house.floors", 20))
        form.addRow("高度（米）", self._double("house.height"))
        form.addRow("屋顶形式", self._line("house.roof_type"))
        form.addRow("地类", self._combo("house.land_type", ["建设用地", "未利用地", "农用地-耕地", "农用地-林地", "农用地-草地", "农用地-其他"]))
        form.addRow("东至", self._line("house.east_boundary"))
        form.addRow("南至", self._line("house.south_boundary"))
        form.addRow("西至", self._line("house.west_boundary"))
        form.addRow("北至", self._line("house.north_boundary"))
        form.addRow("是否征求相邻权利人意见", self._combo("house.neighbor_opinions_requested", ["是", "否"]))
        return panel

    def _build_notice_tab(self) -> QWidget:
        panel, form = self._form_tab()
        form.addRow("公示村名", self._line("public_notice.village_name"))
        form.addRow("联系人", self._line("public_notice.contact_person"))
        form.addRow("联系电话", self._line("public_notice.contact_phone"))
        form.addRow("公示日期", self._line("public_notice.notice_date"))
        self.notice_auto_date = QCheckBox("生成时自动填写当天日期")
        self.notice_auto_date.setProperty("binding", "public_notice.auto_fill_date")
        self.notice_auto_date.toggled.connect(self.schedule_save)
        form.addRow("日期策略", self.notice_auto_date)
        return panel

    def _build_material_tab(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.material_tree = QTreeWidget()
        self.material_tree.setHeaderLabels(["序号", "材料", "状态", "文件"])
        self.material_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.material_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        buttons = QHBoxLayout()
        add_button = QPushButton("上传附件")
        add_button.clicked.connect(self.add_attachment)
        remove_button = QPushButton("移除附件")
        remove_button.clicked.connect(self.remove_attachment)
        generate_word = QPushButton("生成完整材料 Word")
        generate_word.setProperty("generationAction", True)
        generate_word.clicked.connect(lambda: self.generate_document("docx"))
        generate_pdf = QPushButton("生成完整材料 PDF")
        generate_pdf.setProperty("generationAction", True)
        generate_pdf.clicked.connect(lambda: self.generate_document("pdf"))
        buttons.addWidget(add_button)
        buttons.addWidget(remove_button)
        buttons.addStretch(1)
        buttons.addWidget(generate_word)
        buttons.addWidget(generate_pdf)
        layout.addWidget(self.material_tree)
        layout.addLayout(buttons)
        return panel

    def _build_preview_tab(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.pdf_scroll = QScrollArea()
        self.pdf_scroll.setWidgetResizable(True)
        self.pdf_pages = QWidget()
        self.pdf_pages_layout = QVBoxLayout(self.pdf_pages)
        self.pdf_pages_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.pdf_scroll.setWidget(self.pdf_pages)
        buttons = QHBoxLayout()
        regenerate_word = QPushButton("重新生成 Word")
        regenerate_word.setProperty("generationAction", True)
        regenerate_word.clicked.connect(lambda: self.generate_document("docx"))
        regenerate_pdf = QPushButton("重新生成 PDF")
        regenerate_pdf.setProperty("generationAction", True)
        regenerate_pdf.clicked.connect(lambda: self.generate_document("pdf"))
        open_button = QPushButton("打开输出文件")
        open_button.clicked.connect(self.open_output)
        save_as = QPushButton("另存为")
        save_as.clicked.connect(self.save_output_as)
        print_button = QPushButton("打印")
        print_button.clicked.connect(self.print_pdf)
        buttons.addWidget(regenerate_word)
        buttons.addWidget(regenerate_pdf)
        buttons.addStretch(1)
        buttons.addWidget(open_button)
        buttons.addWidget(save_as)
        buttons.addWidget(print_button)
        layout.addWidget(self.pdf_scroll, 1)
        layout.addLayout(buttons)
        return panel

    def refresh_projects(self) -> None:
        selected_id = self.snapshot.id if self.snapshot else ""
        self.project_list.blockSignals(True)
        self.project_list.clear()
        for project in self.projects.repository.list_projects(self.search.text().strip(), "village_house"):
            issues = validate_snapshot(project)
            missing = self.generation.missing_materials(project)
            if project.status == "completed":
                state = "已生成"
            elif issues:
                state = "填写中"
            elif missing:
                state = "附件未完整"
            else:
                state = "可生成"
            item = QListWidgetItem(
                f"{project.applicant.name or '未命名材料'}    ·    {state}\n"
                f"最后更新：{project.updated_at.replace('T', ' ')}"
            )
            item.setData(Qt.ItemDataRole.UserRole, project.id)
            self.project_list.addItem(item)
            if project.id == selected_id:
                item.setSelected(True)
        self.project_list.blockSignals(False)

    def enter_village_house_module(self) -> None:
        self.save_current()
        self.snapshot = None
        self.refresh_projects()
        self.page_stack.setCurrentIndex(1)

    def back_to_home(self) -> None:
        self.save_current()
        self.snapshot = None
        self.page_stack.setCurrentIndex(0)

    def back_to_module(self) -> None:
        if self._worker_thread is not None:
            QMessageBox.information(self, "正在处理", "请等待当前生成或预览任务完成。")
            return
        self.save_current()
        self.snapshot = None
        self.refresh_projects()
        self.page_stack.setCurrentIndex(1)

    def new_project(self) -> None:
        self.save_current()
        self.load_snapshot(self.projects.create_project("village_house"))
        self.refresh_projects()

    def open_selected_project(self) -> None:
        items = self.project_list.selectedItems()
        if not items:
            return
        project_id = items[0].data(Qt.ItemDataRole.UserRole)
        if self.snapshot and project_id == self.snapshot.id:
            return
        self.save_current()
        self.load_snapshot(self.projects.repository.load(project_id))

    def load_snapshot(self, snapshot: ProjectSnapshot) -> None:
        self._loading = True
        self.snapshot = snapshot
        self._clear_preview()
        self.step_menu.setCurrentRow(0)
        self.page_stack.setCurrentIndex(2)
        self.editor_title.setText(snapshot.applicant.name or "未命名材料")
        for widget in self._bound_widgets():
            binding = widget.property("binding")
            if not binding:
                continue
            value = self._get_binding(snapshot, binding)
            if isinstance(widget, QLineEdit):
                widget.setText("" if value is None else str(value))
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setValue(0 if value is None else value)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QComboBox):
                text = "" if value is None else ("是" if value is True else "否" if value is False else str(value))
                widget.setCurrentText(text)
        self.family_table.blockSignals(True)
        self.family_table.setRowCount(max(4, len(snapshot.family_members)))
        self.family_table.clearContents()
        for row, member in enumerate(snapshot.family_members[:4]):
            values = [member.name, member.age, member.relation, member.id_number, member.household_location]
            for column, value in enumerate(values):
                self.family_table.setItem(row, column, QTableWidgetItem("" if value is None else str(value)))
        self.family_table.blockSignals(False)
        self.refresh_materials()
        output_paths = (
            (snapshot.output_docx_path, snapshot.output_pdf_path)
            if snapshot.last_output_format == "docx"
            else (snapshot.output_pdf_path, snapshot.output_docx_path)
        )
        output = next(
            (
                self.projects.root / relative_path
                for relative_path in output_paths
                if relative_path and (self.projects.root / relative_path).is_file()
            ),
            None,
        )
        if output is not None:
            self.step_menu.setCurrentRow(5)
            QTimer.singleShot(0, lambda path=output: self.start_preview(path))
        self._loading = False
        self.statusBar().showMessage("项目已打开", 2500)

    def remove_family_row(self) -> None:
        row = self.family_table.currentRow()
        if row >= 0:
            self.family_table.removeRow(row)
            while self.family_table.rowCount() < 4:
                self.family_table.insertRow(self.family_table.rowCount())
            self.schedule_save()

    def schedule_save(self, *_args) -> None:
        if not self._loading and self.snapshot:
            self._save_timer.start()

    def save_current(self) -> None:
        if not self.snapshot or self._loading:
            return
        self._read_widgets()
        self.projects.repository.save(self.snapshot)
        self.editor_title.setText(self.snapshot.applicant.name or "未命名材料")
        issues = validate_snapshot(self.snapshot)
        message = "已自动保存" if not issues else f"已自动保存；还有 {len(issues)} 项需要完善"
        self.statusBar().showMessage(message, 3500)
        self.refresh_projects()

    def _read_widgets(self) -> None:
        assert self.snapshot is not None
        for widget in self._bound_widgets():
            binding = widget.property("binding")
            if not binding:
                continue
            if isinstance(widget, QLineEdit):
                value = widget.text().strip()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                value = None if widget.value() == 0 else widget.value()
            elif isinstance(widget, QCheckBox):
                value = widget.isChecked()
            else:
                value = widget.currentText()
                if binding == "house.neighbor_opinions_requested":
                    value = True if value == "是" else False if value == "否" else None
            self._set_binding(self.snapshot, binding, value)
        members: list[FamilyMember] = []
        for row in range(self.family_table.rowCount()):
            texts = [(self.family_table.item(row, column).text().strip() if self.family_table.item(row, column) else "") for column in range(5)]
            if not any(texts):
                continue
            try:
                age = int(texts[1]) if texts[1] else None
            except ValueError:
                age = None
            members.append(FamilyMember(texts[0], age, texts[2], texts[3], texts[4]))
        self.snapshot.family_members = members

    def _bound_widgets(self) -> list:
        widgets = []
        for widget_type in (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox):
            widgets.extend(self.findChildren(widget_type))
        return widgets

    @staticmethod
    def _get_binding(snapshot: ProjectSnapshot, binding: str):
        root, name = binding.split(".", 1)
        target = snapshot.proposed_house if root == "house" else getattr(snapshot, root)
        return getattr(target, name)

    @staticmethod
    def _set_binding(snapshot: ProjectSnapshot, binding: str, value) -> None:
        root, name = binding.split(".", 1)
        target = snapshot.proposed_house if root == "house" else getattr(snapshot, root)
        setattr(target, name, value)

    def refresh_materials(self) -> None:
        self.material_tree.clear()
        if not self.snapshot:
            return
        by_code: dict[str, list] = {}
        for attachment in self.snapshot.attachments:
            by_code.setdefault(attachment.material_code, []).append(attachment)
        for material in MATERIALS:
            attachments = by_code.get(material.code, [])
            if material.generated:
                status = "待生成"
            else:
                status = "已上传" if attachments else "缺失"
            if material.code == "11" and len(attachments) < 2:
                status = "缺少远/近照片"
            parent = QTreeWidgetItem([material.code, material.name, status, ""])
            parent.setData(0, Qt.ItemDataRole.UserRole, ("material", material.code))
            self.material_tree.addTopLevelItem(parent)
            for attachment in attachments:
                child = QTreeWidgetItem(["", "附件", "归档" if not attachment.included_in_book else "已上传", Path(attachment.relative_path).name])
                child.setData(0, Qt.ItemDataRole.UserRole, ("attachment", attachment.id))
                parent.addChild(child)
            parent.setExpanded(True)

    def add_attachment(self) -> None:
        if not self.snapshot:
            return
        selected = self.material_tree.currentItem()
        if selected is None:
            QMessageBox.information(self, "上传附件", "请先选择一个材料项目。")
            return
        kind, value = selected.data(0, Qt.ItemDataRole.UserRole)
        code = value if kind == "material" else selected.parent().data(0, Qt.ItemDataRole.UserRole)[1]
        if MATERIAL_BY_CODE[code].generated and code != "11":
            QMessageBox.information(self, "上传附件", "该项目由模板自动生成，不接受普通附件。")
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "选择附件", "", "支持的文件 (*.pdf *.doc *.docx *.jpg *.jpeg *.png *.tif *.tiff *.bmp *.heic *.heif *.dwg *.dxf)")
        for path in paths:
            try:
                self.attachments.add(self.snapshot.id, code, Path(path))
            except Exception as exc:
                QMessageBox.critical(self, "附件上传失败", str(exc))
                break
        self.snapshot = self.projects.repository.load(self.snapshot.id)
        self.refresh_materials()

    def remove_attachment(self) -> None:
        if not self.snapshot:
            return
        selected = self.material_tree.currentItem()
        if selected is None:
            return
        kind, value = selected.data(0, Qt.ItemDataRole.UserRole)
        if kind != "attachment":
            QMessageBox.information(self, "移除附件", "请选择具体附件。")
            return
        attachment = next((item for item in self.snapshot.attachments if item.id == value), None)
        if attachment and QMessageBox.question(self, "确认移除", "确认从当前项目移除该附件？") == QMessageBox.StandardButton.Yes:
            self.attachments.remove(attachment)
            self.snapshot = self.projects.repository.load(self.snapshot.id)
            self.refresh_materials()

    def generate_document(self, output_format: str) -> None:
        if not self.snapshot or self._worker_thread is not None:
            return
        self.save_current()
        issues = validate_snapshot(self.snapshot)
        if issues:
            QMessageBox.warning(self, "信息未完成", "请先处理以下问题：\n" + "\n".join(f"• {item.message}" for item in issues))
            return
        missing = self.generation.missing_materials(self.snapshot)
        allow_incomplete = False
        if missing:
            format_name = "Word" if output_format == "docx" else "PDF"
            message = "缺少以下材料：\n" + "\n".join(f"• {item.material_code} {item.name}：{item.reason}" for item in missing) + f"\n\n是否仍然生成未完整材料 {format_name}？"
            allow_incomplete = QMessageBox.question(self, "材料未完整", message) == QMessageBox.StandardButton.Yes
            if not allow_incomplete:
                return
        self._start_document_worker(
            project_id=self.snapshot.id,
            output_format=output_format,
            allow_incomplete=allow_incomplete,
        )

    def start_preview(self, path: Path) -> None:
        if not self.snapshot or self._worker_thread is not None or not path.exists():
            return
        self._start_document_worker(project_id=self.snapshot.id, preview_source=path)

    def _start_document_worker(
        self,
        *,
        project_id: str,
        output_format: str = "pdf",
        allow_incomplete: bool = False,
        preview_source: Path | None = None,
    ) -> None:
        self._worker_is_generation = preview_source is None
        self._worker_thread = QThread(self)
        self._worker = DocumentWorker(
            self.generation,
            self.projects,
            project_id=project_id,
            output_format=output_format,
            allow_incomplete=allow_incomplete,
            preview_source=preview_source,
        )
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._set_progress)
        self._worker.completed.connect(self._document_ready)
        self._worker.failed.connect(lambda message: QMessageBox.critical(self, "生成失败", message))
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker_thread.finished.connect(self._worker_finished)
        self._set_busy(True)
        self._worker_thread.start()

    def _set_progress(self, message: str) -> None:
        self.progress_label.setText(message)

    def _set_busy(self, busy: bool) -> None:
        self.progress_bar.setVisible(busy)
        if not busy:
            self.progress_label.clear()
        for button in self.findChildren(QPushButton):
            if button.property("generationAction"):
                button.setEnabled(not busy)

    @Slot(str, str, object)
    def _document_ready(self, output_text: str, preview_text: str, page_images: list[bytes]) -> None:
        output = Path(output_text)
        preview = Path(preview_text)
        self._output_path = output
        self._preview_pdf_path = preview
        self._clear_preview(reset_paths=False)
        self._pdf_document = fitz.open(preview)
        for page_number, payload in enumerate(page_images):
            image = QImage()
            image.loadFromData(payload, "PNG")
            label = QLabel()
            label.setPixmap(QPixmap.fromImage(image))
            label.setToolTip(f"第 {page_number + 1} 页")
            label.setStyleSheet("background:white;border:1px solid #bbb;margin:8px")
            self.pdf_pages_layout.addWidget(label)
        if self.snapshot:
            self.snapshot = self.projects.repository.load(self.snapshot.id)
            self.editor_title.setText(self.snapshot.applicant.name or "未命名材料")
        self.step_menu.setCurrentRow(5)
        if self._worker_is_generation:
            QMessageBox.information(self, "生成完成", f"已生成：\n{output}")

    @Slot()
    def _worker_finished(self) -> None:
        thread = self._worker_thread
        self._worker = None
        self._worker_thread = None
        self._set_busy(False)
        if thread is not None:
            thread.deleteLater()

    def load_output(self, path: Path) -> None:
        self.start_preview(path)

    def load_pdf_preview(self, path: Path) -> None:
        self._clear_preview(reset_paths=False)
        self._preview_pdf_path = path
        self._pdf_document = fitz.open(path)
        for page_number, page in enumerate(self._pdf_document):
            pix = page.get_pixmap(matrix=fitz.Matrix(1.15, 1.15), alpha=False)
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
            label = QLabel()
            label.setPixmap(QPixmap.fromImage(image))
            label.setToolTip(f"第 {page_number + 1} 页")
            label.setStyleSheet("background:white;border:1px solid #bbb;margin:8px")
            self.pdf_pages_layout.addWidget(label)

    def _clear_preview(self, *, reset_paths: bool = True) -> None:
        if self._pdf_document is not None:
            self._pdf_document.close()
            self._pdf_document = None
        while self.pdf_pages_layout.count():
            item = self.pdf_pages_layout.takeAt(0)
            if item.widget():
                widget = item.widget()
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        if reset_paths:
            self._output_path = None
            self._preview_pdf_path = None

    def open_output(self) -> None:
        if self._output_path and self._output_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._output_path)))

    def save_output_as(self) -> None:
        if not self._output_path or not self._output_path.exists():
            return
        if self._output_path.suffix.lower() == ".docx":
            title, file_filter = "另存 Word", "Word 文件 (*.docx)"
        else:
            title, file_filter = "另存 PDF", "PDF 文件 (*.pdf)"
        destination, _ = QFileDialog.getSaveFileName(self, title, self._output_path.name, file_filter)
        if destination:
            self.projects.export_document(self._output_path, Path(destination))

    def print_pdf(self) -> None:
        if not self._preview_pdf_path or self._pdf_document is None or self._pdf_document.page_count < 1:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return
        painter = QPainter(printer)
        try:
            for page_number in range(self._pdf_document.page_count):
                if page_number:
                    printer.newPage()
                viewport = painter.viewport()
                page = self._pdf_document.load_page(page_number)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
                scaled = image.scaled(viewport.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                x = viewport.x() + (viewport.width() - scaled.width()) // 2
                y = viewport.y() + (viewport.height() - scaled.height()) // 2
                painter.drawImage(x, y, scaled)
        finally:
            painter.end()

    def delete_current_project(self) -> None:
        if not self.snapshot:
            return
        project = self.snapshot
        if not self._confirm_and_delete_project(project):
            return
        self.snapshot = None
        self._clear_preview()
        self.refresh_projects()
        self.page_stack.setCurrentIndex(1)

    def delete_selected_project(self) -> None:
        items = self.project_list.selectedItems()
        if not items:
            QMessageBox.information(self, "删除材料", "请先选择要删除的材料。")
            return
        project_id = items[0].data(Qt.ItemDataRole.UserRole)
        try:
            project = self.projects.repository.load(project_id)
        except KeyError:
            self.refresh_projects()
            return
        if not self._confirm_and_delete_project(project):
            return
        if self.snapshot and self.snapshot.id == project_id:
            self.snapshot = None
            self._clear_preview()
        self.refresh_projects()

    def _confirm_and_delete_project(self, project: ProjectSnapshot) -> bool:
        name = project.applicant.name or "未命名项目"
        answer = QMessageBox.warning(
            self,
            "确认删除",
            f"确认将“{name}”及其附件移入 Windows 回收站？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        self.projects.delete_project_to_recycle_bin(project.id)
        return True

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker_thread is not None:
            QMessageBox.information(self, "正在处理", "请等待当前生成或预览任务完成后再关闭。")
            event.ignore()
            return
        self.save_current()
        event.accept()
