import sqlite3
from pathlib import Path

from housebook.models import FamilyMember
from housebook.repository import ProjectRepository, SCHEMA_VERSION


def test_project_round_trip(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "app.db")
    project = repository.create_project()
    project.applicant.name = "测试甲"
    project.applicant.id_number = "11010519491231002X"
    project.applicant.household_population = 2
    project.family_members = [FamilyMember(name="测试乙", age=20, relation="子女")]
    project.proposed_house.address = "测试村一组虚构地址"
    project.output_docx_path = "测试.docx"
    project.last_output_format = "docx"
    repository.save(project)

    loaded = repository.load(project.id)
    assert loaded.material_type == "village_house"
    assert loaded.applicant.name == "测试甲"
    assert loaded.family_members[0].name == "测试乙"
    assert loaded.proposed_house.address == "测试村一组虚构地址"
    assert loaded.output_docx_path == "测试.docx"
    assert loaded.last_output_format == "docx"


def test_schema_version(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "app.db")
    with repository.connection() as db:
        assert db.execute("SELECT version FROM schema_version").fetchone()[0] == SCHEMA_VERSION


def test_version_one_database_is_migrated_without_losing_legacy_output(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as db:
        db.executescript(
            """
            CREATE TABLE schema_version(version INTEGER NOT NULL);
            INSERT INTO schema_version VALUES(1);
            CREATE TABLE project(
                id TEXT PRIMARY KEY,status TEXT NOT NULL,created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,output_pdf_path TEXT NOT NULL DEFAULT ''
            );
            INSERT INTO project VALUES('legacy','completed','a','b','old.pdf');
            CREATE TABLE attachment(
                id INTEGER PRIMARY KEY,project_id TEXT,material_code TEXT,relative_path TEXT,
                file_type TEXT,sort_order INTEGER,required INTEGER,included_in_pdf INTEGER,created_at TEXT
            );
            INSERT INTO attachment VALUES(1,'legacy','09','a.jpg','jpg',0,1,0,'now');
            CREATE TABLE generation_run(
                id INTEGER PRIMARY KEY,project_id TEXT,started_at TEXT,finished_at TEXT,status TEXT,
                incomplete INTEGER DEFAULT 0,output_pdf_path TEXT DEFAULT '',error_type TEXT DEFAULT ''
            );
            """
        )

    repository = ProjectRepository(database)
    with repository.connection() as db:
        project = db.execute("SELECT output_pdf_path,output_docx_path,last_output_format,material_type FROM project").fetchone()
        attachment = db.execute("SELECT included_in_pdf,included_in_book FROM attachment").fetchone()
        assert tuple(project) == ("old.pdf", "", "pdf", "village_house")
        assert tuple(attachment) == (0, 0)


def test_projects_are_filtered_by_material_type(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "app.db")
    village = repository.create_project("village_house")
    repository.create_project("future_module")
    assert [item.id for item in repository.list_projects(material_type="village_house")] == [village.id]
