from __future__ import annotations


LIGHT_TOKENS = {
    "canvas": "#F6FAFB",
    "canvas_alt": "#F2F2F7",
    "surface": "#FFFFFF",
    "surface_secondary": "#F7F7FA",
    "text": "#1C1C1E",
    "text_secondary": "#6E6E73",
    "text_tertiary": "#8E8E93",
    "accent": "#28A860",
    "accent_hover": "#239557",
    "accent_pressed": "#1E824C",
    "accent_soft": "#EEF9F2",
    "positive": "#248D52",
    "negative": "#D64545",
    "danger": "#D64545",
    "danger_soft": "#FFF1F0",
    "reward": "#9A6900",
    "reward_soft": "#FFF8E6",
    "separator": "#E7EBE9",
    "separator_strong": "#D7DEDA",
    "selection": "#DDF3E5",
    "scroll": "#C9D2CD",
    "on_accent": "#FFFFFF",
}


DARK_TOKENS = {
    "canvas": "#0F1210",
    "canvas_alt": "#111513",
    "surface": "#1C201E",
    "surface_secondary": "#171A18",
    "text": "#F4F5F4",
    "text_secondary": "#C1C5C2",
    "text_tertiary": "#8E938F",
    "accent": "#48D17B",
    "accent_hover": "#57DC88",
    "accent_pressed": "#3BC26E",
    "accent_soft": "#1B3224",
    "positive": "#57D985",
    "negative": "#FF716B",
    "danger": "#FF6961",
    "danger_soft": "#38201F",
    "reward": "#F1CE72",
    "reward_soft": "#332B18",
    "separator": "#2A302C",
    "separator_strong": "#3A423D",
    "selection": "#22432F",
    "scroll": "#515A54",
    "on_accent": "#0F1210",
}


def build_stylesheet(*, dark: bool = False) -> str:
    """Return the DSByte Qt stylesheet using semantic light/dark tokens."""

    t = DARK_TOKENS if dark else LIGHT_TOKENS
    return f"""
    QMainWindow, QWidget#appRoot, QWidget[page="true"] {{
        background: {t['canvas']};
        color: {t['text']};
    }}
    QWidget {{
        color: {t['text']};
        font-size: 14px;
    }}
    QLabel[role="eyebrow"] {{
        color: {t['accent']};
        font-size: 12px;
        font-weight: 700;
    }}
    QLabel[role="pageTitle"] {{
        color: {t['text']};
        font-size: 30px;
        font-weight: 700;
    }}
    QLabel[role="sectionTitle"] {{
        color: {t['text']};
        font-size: 20px;
        font-weight: 700;
    }}
    QLabel[role="cardTitle"] {{
        color: {t['text']};
        font-size: 17px;
        font-weight: 650;
    }}
    QLabel[role="secondary"] {{
        color: {t['text_secondary']};
        font-size: 14px;
    }}
    QLabel[role="tertiary"] {{
        color: {t['text_tertiary']};
        font-size: 12px;
    }}
    QLabel[role="success"] {{
        color: {t['positive']};
        font-weight: 600;
    }}
    QLabel[role="moduleIcon"] {{
        min-width: 52px;
        max-width: 52px;
        min-height: 52px;
        max-height: 52px;
        color: {t['on_accent']};
        background: {t['accent']};
        border-radius: 14px;
        font-size: 22px;
        font-weight: 700;
    }}
    QLabel[role="tag"] {{
        color: {t['positive']};
        background: {t['accent_soft']};
        border: 1px solid {t['separator']};
        border-radius: 9px;
        padding: 3px 9px;
        font-size: 12px;
        font-weight: 650;
    }}
    QLabel[role="notice"] {{
        color: {t['reward']};
        background: {t['reward_soft']};
        border: 1px solid {t['separator']};
        border-radius: 8px;
        padding: 10px 12px;
    }}
    QLabel[role="emptyTitle"] {{
        color: {t['text']};
        font-size: 17px;
        font-weight: 650;
    }}
    QLabel[role="emptyText"] {{
        color: {t['text_secondary']};
        font-size: 13px;
    }}
    QLabel[role="documentPage"] {{
        background: #FFFFFF;
        border: 1px solid {t['separator_strong']};
        border-radius: 4px;
        margin: 10px;
    }}
    QFrame[role="card"] {{
        background: {t['surface']};
        border: 1px solid {t['separator']};
        border-radius: 14px;
    }}
    QFrame[role="featureCard"] {{
        background: {t['surface']};
        border: 1px solid {t['separator_strong']};
        border-radius: 18px;
    }}
    QFrame[role="softPanel"] {{
        background: {t['surface_secondary']};
        border: 1px solid {t['separator']};
        border-radius: 10px;
    }}
    QPushButton {{
        min-height: 36px;
        padding: 0 14px;
        background: {t['surface']};
        color: {t['text']};
        border: 1px solid {t['separator_strong']};
        border-radius: 8px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background: {t['surface_secondary']};
        border-color: {t['text_tertiary']};
    }}
    QPushButton:pressed {{
        background: {t['canvas_alt']};
    }}
    QPushButton:focus {{
        border: 2px solid {t['accent']};
        padding: 0 13px;
    }}
    QPushButton:disabled {{
        color: {t['text_tertiary']};
        background: {t['surface_secondary']};
        border-color: {t['separator']};
    }}
    QPushButton[role="primary"] {{
        color: {t['on_accent']};
        background: {t['accent']};
        border: 1px solid {t['accent']};
    }}
    QPushButton[role="primary"]:hover {{
        background: {t['accent_hover']};
        border-color: {t['accent_hover']};
    }}
    QPushButton[role="primary"]:pressed {{
        background: {t['accent_pressed']};
        border-color: {t['accent_pressed']};
    }}
    QPushButton[role="ghost"] {{
        color: {t['text_secondary']};
        background: transparent;
        border-color: transparent;
    }}
    QPushButton[role="ghost"]:hover {{
        color: {t['text']};
        background: {t['surface_secondary']};
        border-color: {t['separator']};
    }}
    QPushButton[role="danger"] {{
        color: {t['danger']};
        background: transparent;
        border-color: {t['separator']};
    }}
    QPushButton[role="danger"]:hover {{
        background: {t['danger_soft']};
        border-color: {t['danger']};
    }}
    QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        min-height: 38px;
        padding: 0 10px;
        color: {t['text']};
        background: {t['surface']};
        border: 1px solid {t['separator_strong']};
        border-radius: 8px;
        selection-background-color: {t['accent']};
        selection-color: {t['on_accent']};
    }}
    QLineEdit:hover, QPlainTextEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
        border-color: {t['text_tertiary']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border: 2px solid {t['accent']};
        padding-left: 9px;
    }}
    QLineEdit[role="search"] {{
        min-height: 42px;
        padding-left: 14px;
        background: {t['surface']};
        border-radius: 10px;
    }}
    QPlainTextEdit {{
        padding: 9px 10px;
    }}
    QComboBox::drop-down {{
        width: 28px;
        border: none;
    }}
    QComboBox QAbstractItemView {{
        color: {t['text']};
        background: {t['surface']};
        border: 1px solid {t['separator_strong']};
        selection-background-color: {t['accent_soft']};
        selection-color: {t['text']};
        outline: 0;
    }}
    QCheckBox {{
        spacing: 9px;
        color: {t['text']};
    }}
    QListWidget, QTreeWidget, QTableWidget {{
        color: {t['text']};
        background: {t['surface']};
        alternate-background-color: {t['surface_secondary']};
        border: 1px solid {t['separator']};
        border-radius: 10px;
        outline: 0;
        selection-background-color: {t['accent_soft']};
        selection-color: {t['text']};
    }}
    QListWidget::item {{
        min-height: 48px;
        padding: 8px 12px;
        border-bottom: 1px solid {t['separator']};
    }}
    QListWidget::item:hover {{
        background: {t['surface_secondary']};
    }}
    QListWidget::item:selected {{
        color: {t['text']};
        background: {t['accent_soft']};
        border-left: 3px solid {t['accent']};
        padding-left: 9px;
    }}
    QListWidget[role="steps"] {{
        background: transparent;
        border: none;
        border-radius: 0;
    }}
    QListWidget[role="records"] {{
        border: none;
        border-radius: 0;
    }}
    QListWidget[role="steps"]::item {{
        min-height: 36px;
        margin: 2px 0;
        padding: 7px 10px;
        border: none;
        border-radius: 8px;
        color: {t['text_secondary']};
    }}
    QListWidget[role="steps"]::item:selected {{
        color: {t['accent']};
        background: {t['accent_soft']};
        border: none;
        font-weight: 650;
    }}
    QHeaderView::section {{
        min-height: 38px;
        padding: 0 10px;
        color: {t['text_secondary']};
        background: {t['surface_secondary']};
        border: none;
        border-bottom: 1px solid {t['separator']};
        font-weight: 650;
    }}
    QTableWidget::item, QTreeWidget::item {{
        min-height: 34px;
        padding: 4px 8px;
        border-bottom: 1px solid {t['separator']};
    }}
    QTableWidget::item:selected, QTreeWidget::item:selected {{
        color: {t['text']};
        background: {t['accent_soft']};
    }}
    QScrollArea {{
        background: transparent;
        border: none;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QScrollBar:vertical {{
        width: 12px;
        margin: 2px;
        background: transparent;
    }}
    QScrollBar::handle:vertical {{
        min-height: 32px;
        background: {t['scroll']};
        border-radius: 4px;
        margin: 2px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        height: 0;
        background: transparent;
    }}
    QSplitter::handle {{
        width: 1px;
        background: {t['separator']};
    }}
    QTabWidget::pane {{
        border: none;
        background: transparent;
    }}
    QProgressBar {{
        min-height: 5px;
        max-height: 5px;
        color: transparent;
        background: {t['separator']};
        border: none;
        border-radius: 2px;
    }}
    QProgressBar::chunk {{
        background: {t['accent']};
        border-radius: 2px;
    }}
    QStatusBar {{
        color: {t['text_secondary']};
        background: {t['surface']};
        border-top: 1px solid {t['separator']};
    }}
    QStatusBar::item {{
        border: none;
    }}
    QToolTip {{
        color: {t['text']};
        background: {t['surface']};
        border: 1px solid {t['separator_strong']};
        padding: 6px 8px;
    }}
    QTabWidget::pane {{
        border: none;
        background: transparent;
    }}
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QSplitter::handle {{
        background: transparent;
        width: 10px;
    }}
    QProgressBar {{
        min-height: 7px;
        max-height: 7px;
        background: {t['surface_secondary']};
        border: none;
        border-radius: 3px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: {t['accent']};
        border-radius: 3px;
    }}
    QScrollBar:vertical {{
        width: 10px;
        margin: 2px;
        background: transparent;
    }}
    QScrollBar::handle:vertical {{
        min-height: 28px;
        background: {t['scroll']};
        border-radius: 4px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QStatusBar {{
        color: {t['text_secondary']};
        background: {t['surface']};
        border-top: 1px solid {t['separator']};
    }}
    """
