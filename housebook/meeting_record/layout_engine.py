from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from ..models import MeetingRecordSnapshot
from .template_config import FieldSpec, LineSlot, MeetingTemplate


FORBID_LINE_START = frozenset("，。；：？！、）》】〉〕）］｝”’…％‰℃")
FORBID_LINE_END = frozenset("（《【〈〔［｛“‘")


class MeetingLayoutError(ValueError):
    pass


class FieldOverflowError(MeetingLayoutError):
    def __init__(self, field_key: str, field_label: str) -> None:
        self.field_key = field_key
        self.field_label = field_label
        super().__init__(f"{field_label}内容超出模板可用区域，请缩短后重试")


@dataclass(frozen=True, slots=True)
class GlyphPlacement:
    field_key: str
    char: str
    char_index: int
    page_index: int
    x_mm: float
    baseline_y_mm: float
    font_size: float


@dataclass(frozen=True, slots=True)
class MeetingLayoutResult:
    placements: tuple[GlyphPlacement, ...]
    page_count: int
    field_font_sizes: dict[str, float]


class MeetingLayoutEngine:
    _MEASURE_SCALE = 4

    def __init__(self, template: MeetingTemplate, font_path: Path) -> None:
        self.template = template
        self.font_path = font_path.resolve()
        if not self.font_path.is_file():
            raise MeetingLayoutError("手写字体文件缺失，请重新安装应用")

    def layout(self, record: MeetingRecordSnapshot) -> MeetingLayoutResult:
        values = {
            "meeting_name": record.meeting_name,
            "meeting_time": record.meeting_time,
            "location": record.location,
            "expected_count": "" if record.expected_count is None else str(record.expected_count),
            "actual_count": "" if record.actual_count is None else str(record.actual_count),
            "participants": record.participants,
            "observers": record.observers,
            "chairperson": record.chairperson,
            "recorder": record.recorder,
            "topic": record.topic,
            "content": record.content,
        }
        placements: list[GlyphPlacement] = []
        sizes: dict[str, float] = {}
        for key, spec in self.template.fields.items():
            text = values.get(key, "") or ""
            if not text:
                sizes[key] = spec.font_size
                continue
            if spec.overflow == "continuation":
                field_placements, size = self._layout_continuation(text, spec)
            else:
                field_placements, size = self._layout_fixed(text, spec)
            placements.extend(field_placements)
            sizes[key] = size
        page_count = max((item.page_index for item in placements), default=0) + 1
        return MeetingLayoutResult(tuple(placements), page_count, sizes)

    def _layout_fixed(self, text: str, spec: FieldSpec) -> tuple[list[GlyphPlacement], float]:
        size = spec.font_size
        while size >= spec.min_font_size - 0.001:
            result = self._try_layout(text, spec, spec.lines, size)
            if result is not None:
                return result, size
            size -= 0.5
        raise FieldOverflowError(spec.key, spec.label)

    def _layout_continuation(self, text: str, spec: FieldSpec) -> tuple[list[GlyphPlacement], float]:
        slots = list(spec.lines)
        for page_index in range(1, 201):
            result = self._try_layout(text, spec, tuple(slots), spec.font_size)
            if result is not None:
                return result, spec.font_size
            slots.extend(replace(slot, page_index=page_index) for slot in self.template.continuation_lines)
        raise FieldOverflowError(spec.key, spec.label)

    def _try_layout(
        self,
        text: str,
        spec: FieldSpec,
        slots: tuple[LineSlot, ...],
        font_size: float,
    ) -> list[GlyphPlacement] | None:
        if not slots:
            return [] if not text else None
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        slot_index = 0
        current: list[tuple[str, int, float]] = []
        results: list[GlyphPlacement] = []

        def commit_line(carry: list[tuple[str, int, float]] | None = None) -> bool:
            nonlocal slot_index, current
            if slot_index >= len(slots):
                return False
            slot = slots[slot_index]
            x = slot.x1_mm
            for char, char_index, width in current:
                results.append(
                    GlyphPlacement(
                        field_key=spec.key,
                        char=char,
                        char_index=char_index,
                        page_index=slot.page_index,
                        x_mm=x,
                        baseline_y_mm=slot.baseline_y_mm,
                        font_size=font_size,
                    )
                )
                x += width + spec.spacing_mm
            slot_index += 1
            current = list(carry or [])
            return True

        index = 0
        while index < len(normalized):
            char = normalized[index]
            if char == "\n":
                if not commit_line():
                    return None
                index += 1
                continue
            if slot_index >= len(slots):
                return None
            width = self._char_width_mm(char, font_size)
            slot = slots[slot_index]
            used = sum(item[2] for item in current) + spec.spacing_mm * max(0, len(current) - 1)
            if current and self._is_atomic_character(char) and (
                index == 0 or not self._is_atomic_character(normalized[index - 1])
            ):
                end = index
                token_width = 0.0
                token_count = 0
                while end < len(normalized) and self._is_atomic_character(normalized[end]):
                    token_width += self._char_width_mm(normalized[end], font_size)
                    token_count += 1
                    end += 1
                token_width += spec.spacing_mm * max(0, token_count - 1)
                line_width = slot.x2_mm - slot.x1_mm
                remaining = line_width - used - spec.spacing_mm
                if token_width <= line_width and token_width > remaining:
                    if not commit_line():
                        return None
                    continue
            fits = used + (spec.spacing_mm if current else 0.0) + width <= slot.x2_mm - slot.x1_mm
            if fits:
                current.append((char, index, width))
                index += 1
                continue
            if not current:
                return None

            carry: list[tuple[str, int, float]] = []
            if char in FORBID_LINE_START and len(current) > 1:
                carry.insert(0, current.pop())
            while current and current[-1][0] in FORBID_LINE_END:
                carry.insert(0, current.pop())
            if not current:
                return None
            if not commit_line(carry):
                return None
        if current and not commit_line():
            return None
        return results

    @staticmethod
    def _is_atomic_character(char: str) -> bool:
        return char.isascii() and (char.isalnum() or char in "._:/+-@") or char in "年月日时分秒"

    @lru_cache(maxsize=512)
    def _font(self, size_px: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(self.font_path), size_px)

    @lru_cache(maxsize=8192)
    def _char_width_mm(self, char: str, font_size: float) -> float:
        px_size = max(1, round(font_size * self._MEASURE_SCALE))
        width_px = self._font(px_size).getlength(char)
        return max(0.1, width_px / self._MEASURE_SCALE * 25.4 / 72.0)
