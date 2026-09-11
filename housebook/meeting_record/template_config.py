from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..paths import resource_path


@dataclass(frozen=True, slots=True)
class LineSlot:
    page_index: int
    x1_mm: float
    x2_mm: float
    baseline_y_mm: float


@dataclass(frozen=True, slots=True)
class FieldSpec:
    key: str
    label: str
    font_size: float
    min_font_size: float
    spacing_mm: float
    lines: tuple[LineSlot, ...]
    overflow: str = "error"


@dataclass(frozen=True, slots=True)
class MeetingTemplate:
    template_id: str
    version: int
    name: str
    description: str
    root: Path
    first_page_pdf: Path
    continuation_page_pdf: Path
    thumbnail: Path
    page_width_mm: float
    page_height_mm: float
    fields: dict[str, FieldSpec]
    continuation_lines: tuple[LineSlot, ...]


class MeetingTemplateRegistry:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or resource_path("templates", "meeting_record")).resolve()

    def templates(self) -> tuple[MeetingTemplate, ...]:
        manifests = sorted(self.root.glob("*/template.json"))
        return tuple(self._load(path) for path in manifests)

    def get(self, template_id: str, version: int) -> MeetingTemplate:
        for template in self.templates():
            if template.template_id == template_id and template.version == version:
                return template
        raise KeyError(f"会议模板不存在：{template_id} v{version}")

    @staticmethod
    def _load(path: Path) -> MeetingTemplate:
        payload = json.loads(path.read_text(encoding="utf-8"))
        root = path.parent

        def slots(items: list[dict], *, page_index: int = 0) -> tuple[LineSlot, ...]:
            return tuple(
                LineSlot(
                    page_index=int(item.get("page_index", page_index)),
                    x1_mm=float(item["x1_mm"]),
                    x2_mm=float(item["x2_mm"]),
                    baseline_y_mm=float(item["baseline_y_mm"]),
                )
                for item in items
            )

        fields = {
            key: FieldSpec(
                key=key,
                label=str(item["label"]),
                font_size=float(item["font_size"]),
                min_font_size=float(item["min_font_size"]),
                spacing_mm=float(item.get("spacing_mm", 0.4)),
                lines=slots(item["lines"]),
                overflow=str(item.get("overflow", "error")),
            )
            for key, item in payload["fields"].items()
        }
        return MeetingTemplate(
            template_id=str(payload["template_id"]),
            version=int(payload["version"]),
            name=str(payload["name"]),
            description=str(payload.get("description", "")),
            root=root,
            first_page_pdf=root / payload["pages"]["first"]["base_pdf"],
            continuation_page_pdf=root / payload["pages"]["continuation"]["base_pdf"],
            thumbnail=root / payload["thumbnail"],
            page_width_mm=float(payload["page"]["width_mm"]),
            page_height_mm=float(payload["page"]["height_mm"]),
            fields=fields,
            continuation_lines=slots(payload["pages"]["continuation"]["content_lines"], page_index=1),
        )
