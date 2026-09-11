from __future__ import annotations

from pathlib import Path

import pytest

from housebook.meeting_record.handwriting_engine import HandwritingRenderer
from housebook.meeting_record.layout_engine import FieldOverflowError, MeetingLayoutEngine
from housebook.meeting_record.template_config import MeetingTemplateRegistry
from housebook.models import MeetingRecordSnapshot
from housebook.paths import resource_path


FONT = resource_path("fonts", "handwriting", "LXGWWenKaiGBLite-Regular.ttf")


def _engine() -> MeetingLayoutEngine:
    template = MeetingTemplateRegistry().get("standard_meeting_record", 1)
    return MeetingLayoutEngine(template, FONT)


@pytest.mark.parametrize(
    ("line_count", "expected_pages"),
    ((9, 1), (10, 2), (31, 2), (32, 3)),
)
def test_content_flows_from_first_page_to_repeatable_continuations(
    line_count: int, expected_pages: int
) -> None:
    record = MeetingRecordSnapshot(id="layout")
    record.content = "\n".join(f"第{index + 1}行" for index in range(line_count))
    result = _engine().layout(record)
    assert result.page_count == expected_pages
    assert "".join(item.char for item in result.placements if item.field_key == "content") == record.content.replace("\n", "")


def test_explicit_blank_lines_are_consumed_without_losing_following_text() -> None:
    record = MeetingRecordSnapshot(id="blank-lines")
    record.content = "第一行\n\n第四行"
    result = _engine().layout(record)
    baselines = [
        item.baseline_y_mm for item in result.placements if item.field_key == "content"
    ]
    assert min(baselines) < max(baselines)
    assert "".join(item.char for item in result.placements) == "第一行第四行"


def test_fixed_field_overflow_names_the_field_and_never_truncates() -> None:
    record = MeetingRecordSnapshot(id="overflow", participants="参" * 1000)
    with pytest.raises(FieldOverflowError, match="参加人员"):
        _engine().layout(record)


def test_same_record_layout_is_deterministic_and_seed_does_not_change_line_breaks() -> None:
    first = MeetingRecordSnapshot(id="one", content="中文标点（测试）与 English-2026 连续内容。")
    second = MeetingRecordSnapshot(id="two", content=first.content, handwriting_seed=first.handwriting_seed + 1)
    left = _engine().layout(first)
    right = _engine().layout(second)
    assert left.placements == right.placements
    assert left.page_count == right.page_count


def test_font_preflight_reports_unsupported_character() -> None:
    renderer = HandwritingRenderer(FONT)
    assert "\U0001f600" in renderer.missing_characters(["常用简体字\U0001f600"])
