from __future__ import annotations

from pathlib import Path

import fitz

from PySide6.QtCore import QObject, QSize, QThread, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices, QImage, QPageLayout, QPageSize, QPainter, QPalette, QPixmap
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QProgressBar, QScrollArea, QSpinBox, QSplitter, QStackedWidget, QStatusBar, QTabWidget,
    QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..constants import MATERIALS, MATERIAL_BY_CODE
from ..models import FamilyMember, ProjectSnapshot
from ..validation import validate_snapshot
from ..services.attachment_service import AttachmentService
from ..services.generation_service import GenerationService
from ..services.project_service import ProjectService
from .meeting_record_page import MeetingRecordModulePage
from .theme import build_stylesheet


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
        self.setObjectName("appRoot")
        self.resize(1360, 880)
        self.setMinimumSize(1040, 700)
        is_dark = QApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128
        self.setStyleSheet(build_stylesheet(dark=is_dark))
        self.setStatusBar(QStatusBar())
        self._build_ui()
        self.refresh_projects()

    def _build_ui(self) -> None:
        self.page_stack = QStackedWidget()
        self.page_stack.addWidget(self._build_home_page())
        self.page_stack.addWidget(self._build_module_page())
        self.page_stack.addWidget(self._build_editor_page())
        self.meeting_page = MeetingRecordModulePage(self.projects)
        self.meeting_page.back_requested.connect(self.back_to_home)
        self.page_stack.addWidget(self.meeting_page)
        self.setCentralWidget(self.page_stack)
        self.page_stack.setCurrentIndex(0)

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

    def _build_home_page(self) -> QWidget:
        page = QWidget()
        page.setProperty("page", True)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(64, 40, 64, 56)
        layout.setSpacing(0)

        top = QHBoxLayout()
        brand = self._label("村务材料管理", "cardTitle")
        version = self._label("本地安全 · 1.1", "tag")
        top.addWidget(brand)
        top.addStretch(1)
        top.addWidget(version)
        layout.addLayout(top)
        layout.addStretch(1)

        hero = QWidget()
        hero.setMaximumWidth(960)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        hero_layout.setSpacing(12)
        hero_layout.addWidget(self._label("VILLAGE DOCUMENTS", "eyebrow"))
        hero_layout.addWidget(self._label("把村建材料，清楚地办完", "pageTitle"))
        hero_layout.addWidget(
            self._label("从信息录入、附件整理到 Word / PDF 成册，所有资料仅保存在这台电脑。", "secondary", word_wrap=True)
        )
        layout.addWidget(hero)
        layout.addSpacing(32)

        module_card = self._card("featureCard")
        module_card.setMaximumWidth(960)
        module_layout = QHBoxLayout(module_card)
        module_layout.setContentsMargins(28, 26, 28, 26)
        module_layout.setSpacing(20)
        module_icon = self._label("村", "moduleIcon")
        module_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        module_layout.addWidget(module_icon, 0, Qt.AlignmentFlag.AlignTop)
        module_copy = QVBoxLayout()
        module_copy.setSpacing(7)
        module_copy.addWidget(self._label("村建材料", "sectionTitle"))
        module_copy.addWidget(
            self._label("村民建房报备材料自动填写、附件归档与合并成册。", "secondary", word_wrap=True)
        )
        module_copy.addSpacing(8)
        module_copy.addWidget(self._label("固定母版  ·  自动保存  ·  离线处理", "tertiary"))
        module_layout.addLayout(module_copy, 1)
        enter_button = self._button("进入办理  →", "primary")
        enter_button.setMinimumWidth(126)
        enter_button.clicked.connect(self.enter_village_house_module)
        module_layout.addWidget(enter_button, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(module_card)
        layout.addSpacing(18)

        meeting_card = self._card("featureCard")
        meeting_card.setMaximumWidth(960)
        meeting_layout = QHBoxLayout(meeting_card)
        meeting_layout.setContentsMargins(28, 26, 28, 26)
        meeting_layout.setSpacing(20)
        meeting_icon = self._label("会", "moduleIcon")
        meeting_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        meeting_layout.addWidget(meeting_icon, 0, Qt.AlignmentFlag.AlignTop)
        meeting_copy = QVBoxLayout()
        meeting_copy.setSpacing(7)
        meeting_copy.addWidget(self._label("会议记录", "sectionTitle"))
        meeting_copy.addWidget(
            self._label("按标准会议记录纸填写内容，生成自然手写效果 PDF。", "secondary", word_wrap=True)
        )
        meeting_copy.addSpacing(8)
        meeting_copy.addWidget(self._label("模板排版  ·  自动续页  ·  可预览打印", "tertiary"))
        meeting_layout.addLayout(meeting_copy, 1)
        meeting_enter = self._button("进入记录  →", "primary")
        meeting_enter.setMinimumWidth(126)
        meeting_enter.clicked.connect(self.enter_meeting_record_module)
        meeting_layout.addWidget(meeting_enter, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(meeting_card)
        layout.addSpacing(18)
        layout.addWidget(self._label("选择材料类型后，可以新建办理记录或继续上次工作。", "tertiary"))
        layout.addStretch(1)
        return page

    def _build_module_page(self) -> QWidget:
        page = QWidget()
        page.setProperty("page", True)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 28, 40, 36)
        layout.setSpacing(18)
        header = QHBoxLayout()
        back = self._button("←  材料类型", "ghost")
        back.clicked.connect(self.back_to_home)
        heading = QVBoxLayout()
        heading.setSpacing(3)
        heading.addWidget(self._label("村建材料", "pageTitle"))
        heading.addWidget(self._label("管理办理记录，双击任意记录即可继续填写。", "secondary"))
        new_button = self._button("＋  新建材料", "primary")
        new_button.setMinimumWidth(130)
        new_button.clicked.connect(self.new_project)
        header.addWidget(back)
        header.addSpacing(8)
        header.addLayout(heading)
        header.addStretch(1)
        header.addWidget(new_button)

        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setProperty("role", "search")
        self.search.setPlaceholderText("搜索申请人姓名…")
        self.search.setMaximumWidth(420)
        self.search.textChanged.connect(self.refresh_projects)
        self.project_count_label = self._label("0 份材料", "tertiary")
        toolbar.addWidget(self.search, 1)
        toolbar.addStretch(1)
        toolbar.addWidget(self.project_count_label)

        records_card = self._card()
        records_layout = QVBoxLayout(records_card)
        records_layout.setContentsMargins(0, 0, 0, 14)
        records_layout.setSpacing(0)
        self.project_list = QListWidget()
        self.project_list.setProperty("role", "records")
        self.project_list.setSpacing(0)
        self.project_list.setAlternatingRowColors(False)
        self.project_list.itemDoubleClicked.connect(lambda _item: self.open_selected_project())
        records_layout.addWidget(self.project_list, 1)

        self.project_empty = QWidget()
        empty_layout = QVBoxLayout(self.project_empty)
        empty_layout.setContentsMargins(32, 72, 32, 72)
        empty_layout.setSpacing(8)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.project_empty_title = self._label("还没有办理记录", "emptyTitle")
        self.project_empty_text = self._label("新建第一份材料后，填写进度会显示在这里。", "emptyText")
        empty_layout.addWidget(self.project_empty_title, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addWidget(self.project_empty_text, 0, Qt.AlignmentFlag.AlignHCenter)
        first_button = self._button("新建第一份材料", "primary")
        first_button.clicked.connect(self.new_project)
        empty_layout.addSpacing(8)
        empty_layout.addWidget(first_button, 0, Qt.AlignmentFlag.AlignHCenter)
        records_layout.addWidget(self.project_empty, 1)

        self.open_project_button = self._button("打开选中材料")
        self.open_project_button.clicked.connect(self.open_selected_project)
        self.delete_project_button = self._button("删除选中材料", "danger")
        self.delete_project_button.clicked.connect(self.delete_selected_project)
        self.project_list.itemSelectionChanged.connect(self._update_project_actions)
        actions = QHBoxLayout()
        actions.setContentsMargins(14, 14, 14, 0)
        actions.addStretch(1)
        actions.addWidget(self.delete_project_button)
        actions.addWidget(self.open_project_button)
        records_layout.addLayout(actions)

        layout.addLayout(header)
        layout.addLayout(toolbar)
        layout.addWidget(records_card, 1)
        return page

    def _build_editor_page(self) -> QWidget:
        page = QWidget()
        page.setProperty("page", True)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(20, 16, 20, 20)
        outer.setSpacing(12)
        header = QHBoxLayout()
        back = self._button("←  材料列表", "ghost")
        back.clicked.connect(self.back_to_module)
        title_stack = QVBoxLayout()
        title_stack.setSpacing(1)
        self.editor_title = self._label("未命名材料", "sectionTitle")
        title_stack.addWidget(self.editor_title)
        title_stack.addWidget(self._label("村建材料办理记录", "tertiary"))
        delete_button = self._button("删除当前材料", "danger")
        delete_button.clicked.connect(self.delete_current_project)
        header.addWidget(back)
        header.addSpacing(6)
        header.addLayout(title_stack)
        header.addStretch(1)
        header.addWidget(delete_button)
        self.progress_label = QLabel("")
        self.progress_label.setProperty("role", "success")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setMaximumWidth(240)
        self.progress_bar.hide()
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress_label)
        progress_row.addStretch(1)
        progress_row.addWidget(self.progress_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        step_panel = self._card()
        step_layout = QVBoxLayout(step_panel)
        step_layout.setContentsMargins(14, 18, 14, 16)
        step_layout.setSpacing(6)
        step_layout.addWidget(self._label("办理流程", "cardTitle"))
        step_layout.addWidget(self._label("信息会自动保存", "tertiary"))
        step_layout.addSpacing(8)
        self.step_menu = QListWidget()
        self.step_menu.setProperty("role", "steps")
        self.step_menu.addItems(
            ["01   申请人信息", "02   家庭成员", "03   宅基地及住房", "04   公示信息", "05   材料清单", "06   生成预览"]
        )
        step_layout.addWidget(self.step_menu, 1)
        step_layout.addWidget(self._label("填写内容仅保存在本机", "tertiary"))
        step_panel.setMinimumWidth(210)
        step_panel.setMaximumWidth(238)

        content_panel = self._card()
        content_layout = QVBoxLayout(content_panel)
        content_layout.setContentsMargins(28, 24, 28, 24)
        content_layout.setSpacing(6)
        self.section_title = self._label("申请人信息", "sectionTitle")
        self.section_description = self._label("填写申请人的身份与户籍信息。", "secondary")
        content_layout.addWidget(self.section_title)
        content_layout.addWidget(self.section_description)
        content_layout.addSpacing(10)
        content_layout.addWidget(self._build_editor(), 1)

        self.step_menu.currentRowChanged.connect(self._set_editor_step)
        splitter.addWidget(step_panel)
        splitter.addWidget(content_panel)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 1080])
        outer.addLayout(header)
        outer.addLayout(progress_row)
        outer.addWidget(splitter, 1)
        self.step_menu.setCurrentRow(0)
        return page

    def _set_editor_step(self, row: int) -> None:
        steps = (
            ("申请人信息", "填写申请人的身份、联系方式与户籍信息。"),
            ("家庭成员", "维护家庭成员信息，母版最多打印四名成员。"),
            ("宅基地及住房", "填写现有宅基地、拟建住房与四至信息。"),
            ("公示信息", "设置公示联系人、联系电话与日期策略。"),
            ("材料清单", "核对自动生成材料并补充需要上传的附件。"),
            ("生成预览", "查看合并结果，打开、另存或打印最终材料。"),
        )
        index = max(0, min(row, len(steps) - 1))
        self.tabs.setCurrentIndex(index)
        title, description = steps[index]
        self.section_title.setText(title)
        self.section_description.setText(description)

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
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        form_content = QWidget()
        form_content.setMaximumWidth(880)
        form = QFormLayout(form_content)
        form.setContentsMargins(2, 6, 24, 24)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(14)
        scroll.setWidget(form_content)
        panel_layout.addWidget(scroll)
        return panel, form

    def _form_section(self, form: QFormLayout, text: str) -> None:
        label = self._label(text, "eyebrow")
        label.setContentsMargins(0, 12, 0, 2)
        form.addRow(label)

    def _build_applicant_tab(self) -> QWidget:
        panel, form = self._form_tab()
        self._form_section(form, "基本信息")
        form.addRow("姓名 *", self._line("applicant.name"))
        form.addRow("性别", self._combo("applicant.gender", ["男", "女"]))
        form.addRow("年龄", self._spin("applicant.age"))
        form.addRow("身份证号 *", self._line("applicant.id_number"))
        form.addRow("联系电话", self._line("applicant.phone"))
        self._form_section(form, "户籍信息")
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
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(14)
        note = self._label("提示：申请表母版最多打印四名家庭成员；超出的成员会保存，但不会写入该母版。", "notice")
        self.family_table = QTableWidget(4, 5)
        self.family_table.setHorizontalHeaderLabels(["姓名", "年龄", "与户主关系", "身份证号", "户口所在地"])
        self.family_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.family_table.verticalHeader().setVisible(False)
        self.family_table.setAlternatingRowColors(True)
        self.family_table.setMinimumHeight(260)
        self.family_table.itemChanged.connect(self.schedule_save)
        buttons = QHBoxLayout()
        add_row = self._button("＋  添加家庭成员")
        add_row.clicked.connect(lambda: self.family_table.insertRow(self.family_table.rowCount()))
        remove_row = self._button("移除选中成员", "danger")
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
        self._form_section(form, "现有宅基地与住房")
        form.addRow("现宅基地面积（㎡）", self._double("existing_house.homestead_area"))
        form.addRow("现住房建筑面积（㎡）", self._double("existing_house.building_area"))
        form.addRow("权属证书号", self._line("existing_house.ownership_certificate_no"))
        form.addRow("现宅基地处置方式", self._line("existing_house.disposal_type"))
        form.addRow("保留面积（㎡）", self._double("existing_house.disposal_area"))
        self._form_section(form, "拟建住房")
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
        self._form_section(form, "四至与相邻意见")
        form.addRow("东至", self._line("house.east_boundary"))
        form.addRow("南至", self._line("house.south_boundary"))
        form.addRow("西至", self._line("house.west_boundary"))
        form.addRow("北至", self._line("house.north_boundary"))
        form.addRow("是否征求相邻权利人意见", self._combo("house.neighbor_opinions_requested", ["是", "否"]))
        return panel

    def _build_notice_tab(self) -> QWidget:
        panel, form = self._form_tab()
        self._form_section(form, "公示落款")
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
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(14)
        self.material_tree = QTreeWidget()
        self.material_tree.setHeaderLabels(["序号", "材料", "状态", "文件"])
        self.material_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.material_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.material_tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.material_tree.setAlternatingRowColors(True)
        buttons = QHBoxLayout()
        add_button = self._button("＋  上传附件")
        add_button.clicked.connect(self.add_attachment)
        remove_button = self._button("移除附件", "danger")
        remove_button.clicked.connect(self.remove_attachment)
        generate_word = self._button("生成完整材料 Word")
        generate_word.setProperty("generationAction", True)
        generate_word.clicked.connect(lambda: self.generate_document("docx"))
        generate_pdf = self._button("生成完整材料 PDF", "primary")
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
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(14)
        self.pdf_scroll = QScrollArea()
        self.pdf_scroll.setWidgetResizable(True)
        self.pdf_pages = QWidget()
        self.pdf_pages_layout = QVBoxLayout(self.pdf_pages)
        self.pdf_pages_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.pdf_scroll.setWidget(self.pdf_pages)
        buttons = QHBoxLayout()
        regenerate_word = self._button("重新生成 Word")
        regenerate_word.setProperty("generationAction", True)
        regenerate_word.clicked.connect(lambda: self.generate_document("docx"))
        regenerate_pdf = self._button("重新生成 PDF")
        regenerate_pdf.setProperty("generationAction", True)
        regenerate_pdf.clicked.connect(lambda: self.generate_document("pdf"))
        open_button = self._button("打开输出文件", "primary")
        open_button.clicked.connect(self.open_output)
        save_as = self._button("另存为")
        save_as.clicked.connect(self.save_output_as)
        print_button = self._button("打印")
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
        projects = self.projects.repository.list_projects(self.search.text().strip(), "village_house")
        self.project_list.blockSignals(True)
        self.project_list.clear()
        for project in projects:
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
            item.setSizeHint(QSize(0, 66))
            item.setToolTip("双击继续办理")
            self.project_list.addItem(item)
            if project.id == selected_id:
                item.setSelected(True)
        self.project_list.blockSignals(False)
        self.project_count_label.setText(f"{len(projects)} 份材料")
        is_empty = not projects
        self.project_empty.setVisible(is_empty)
        self.project_list.setVisible(not is_empty)
        if is_empty and self.search.text().strip():
            self.project_empty_title.setText("没有找到匹配记录")
            self.project_empty_text.setText("请检查申请人姓名，或清空搜索后再试。")
        else:
            self.project_empty_title.setText("还没有办理记录")
            self.project_empty_text.setText("新建第一份材料后，填写进度会显示在这里。")
        self._update_project_actions()

    def _update_project_actions(self) -> None:
        has_selection = bool(self.project_list.selectedItems())
        self.open_project_button.setEnabled(has_selection)
        self.delete_project_button.setEnabled(has_selection)

    def enter_village_house_module(self) -> None:
        self.save_current()
        self.snapshot = None
        self.refresh_projects()
        self.page_stack.setCurrentIndex(1)

    def enter_meeting_record_module(self) -> None:
        if self._worker_thread is not None:
            QMessageBox.information(self, "正在处理", "请等待当前生成或预览任务完成。")
            return
        self.save_current()
        self.snapshot = None
        self.meeting_page.enter()
        self.page_stack.setCurrentWidget(self.meeting_page)

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
            label.setProperty("role", "documentPage")
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
            label.setProperty("role", "documentPage")
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
        if not self.meeting_page.can_close():
            event.ignore()
            return
        self.save_current()
        event.accept()
