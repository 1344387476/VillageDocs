from __future__ import annotations

from pathlib import Path

import fitz

from housebook.meeting_record.generation_service import MeetingRecordGenerationService
from housebook.services.project_service import ProjectService


def test_empty_meeting_record_generates_one_a4_page_with_vector_template(tmp_path: Path) -> None:
    projects = ProjectService(tmp_path / "workspace")
    record = projects.create_meeting_record()
    output = MeetingRecordGenerationService(projects).generate(record.id)

    assert output.name.startswith("未命名_会议记录_")
    with fitz.open(output) as document:
        assert document.page_count == 1
        page = document[0]
        assert abs(page.rect.width - 595.28) < 1
        assert abs(page.rect.height - 841.89) < 1
        assert "会议名称" in page.get_text()
        assert len(page.get_drawings()) > 10
        assert len(page.get_images(full=True)) == 1


def test_generation_reuses_seed_and_adds_numbered_filename(tmp_path: Path) -> None:
    projects = ProjectService(tmp_path / "workspace")
    record = projects.create_meeting_record()
    record.meeting_name = "虚构测试会议"
    record.content = "第一项内容。\n第二项内容。"
    projects.repository.save_meeting_record(record)
    service = MeetingRecordGenerationService(projects)

    first = service.generate(record.id)
    second = service.generate(record.id)

    assert first != second
    assert second.stem.endswith("_2")
    with fitz.open(first) as left, fitz.open(second) as right:
        assert left.page_count == right.page_count == 1
        assert left[0].get_pixmap(alpha=False).digest == right[0].get_pixmap(alpha=False).digest
