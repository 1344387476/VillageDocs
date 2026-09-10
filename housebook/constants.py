from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FieldKind(StrEnum):
    AUTO = "AUTO"
    SIGNATURE = "SIGNATURE"
    STAMP = "STAMP"
    MANUAL_ONLY = "MANUAL_ONLY"


@dataclass(frozen=True, slots=True)
class MaterialDefinition:
    code: str
    name: str
    order: int
    mode: str
    required: bool = True
    generated: bool = False


@dataclass(frozen=True, slots=True)
class MaterialModuleDefinition:
    code: str
    name: str
    description: str


MATERIAL_MODULES: tuple[MaterialModuleDefinition, ...] = (
    MaterialModuleDefinition("village_house", "村建材料", "村民建房报备材料自动填写、附件整理与成册"),
)
MATERIAL_MODULE_BY_CODE = {item.code: item for item in MATERIAL_MODULES}


MATERIALS: tuple[MaterialDefinition, ...] = (
    MaterialDefinition("01", "申请表", 1, "template", generated=True),
    MaterialDefinition("02", "审批表", 2, "template", generated=True),
    MaterialDefinition("03", "农村宅基地使用承诺书", 3, "template", generated=True),
    MaterialDefinition("04", "建房申请书", 4, "template", generated=True),
    MaterialDefinition("05", "唯一住房证明", 5, "template", generated=True),
    MaterialDefinition("06", "镇政府承诺书", 6, "template", generated=True),
    MaterialDefinition("07", "四邻意见", 7, "template", generated=True),
    MaterialDefinition("08", "户口簿复印件", 8, "attachment"),
    MaterialDefinition("09", "身份证复印件", 9, "attachment"),
    MaterialDefinition("10", "村民委员会会议记录", 10, "attachment"),
    MaterialDefinition("11", "建房公示及远近照片", 11, "template_and_photos", generated=True),
    MaterialDefinition("13", "宅基地坐落平面图", 13, "attachment"),
    MaterialDefinition("14", "土地权属材料", 14, "attachment"),
)

MATERIAL_BY_CODE = {item.code: item for item in MATERIALS}
GENERATED_CODES = tuple(item.code for item in MATERIALS if item.generated)
REQUIRED_ATTACHMENT_CODES = ("08", "09", "10", "13", "14")
BOOK_ORDER = tuple(item.code for item in MATERIALS)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".heic", ".heif"}
WORD_SUFFIXES = {".doc", ".docx"}
PDF_SUFFIXES = {".pdf"}
CAD_SUFFIXES = {".dwg", ".dxf"}
SUPPORTED_SUFFIXES = IMAGE_SUFFIXES | WORD_SUFFIXES | PDF_SUFFIXES | CAD_SUFFIXES
