from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from housebook.repository import ProjectRepository, SCHEMA_VERSION


def test_meeting_record_round_trip_search_and_template_lock(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "app.db")
    record = repository.create_meeting_record("standard_meeting_record", 1)
    record.meeting_name = "虚构村民代表会议"
    record.meeting_time = "2026年9月11日上午"
    record.topic = "虚构环境整治议题"
    record.expected_count = 28
    repository.save_meeting_record(record)

    loaded = repository.load_meeting_record(record.id)
    assert loaded.material_type == "meeting_record"
    assert loaded.expected_count == 28
    assert loaded.handwriting_seed == record.handwriting_seed
    assert [item.id for item in repository.list_meeting_records("环境整治")] == [record.id]
    assert repository.list_projects(material_type="village_house") == []

    loaded.template_version = 2
    with pytest.raises(ValueError, match="不能更换模板"):
        repository.save_meeting_record(loaded)


def test_schema_three_migrates_to_meeting_table_without_changing_village_row(
    tmp_path: Path,
) -> None:
    database = tmp_path / "schema-3.db"
    with sqlite3.connect(database) as db:
        db.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE schema_version(version INTEGER NOT NULL);
            INSERT INTO schema_version VALUES(3);
            CREATE TABLE project(
                id TEXT PRIMARY KEY, material_type TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                output_pdf_path TEXT NOT NULL DEFAULT '', output_docx_path TEXT NOT NULL DEFAULT '',
                last_output_format TEXT NOT NULL DEFAULT ''
            );
            INSERT INTO project VALUES('village','village_house','completed','a','b','old.pdf','old.docx','docx');
            """
        )

    repository = ProjectRepository(database)
    with repository.connection() as db:
        assert db.execute("SELECT version FROM schema_version").fetchone()[0] == SCHEMA_VERSION
        row = db.execute(
            "SELECT material_type,output_pdf_path,output_docx_path,last_output_format FROM project"
        ).fetchone()
        assert tuple(row) == ("village_house", "old.pdf", "old.docx", "docx")
        assert db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='meeting_record'"
        ).fetchone() is not None


def test_deleting_meeting_project_cascades_payload(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "app.db")
    record = repository.create_meeting_record()
    repository.delete_project_record(record.id)
    with repository.connection() as db:
        assert db.execute(
            "SELECT 1 FROM meeting_record WHERE project_id=?", (record.id,)
        ).fetchone() is None
