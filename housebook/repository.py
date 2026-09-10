from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .models import Applicant, Attachment, ExistingHouse, FamilyMember, ProjectSnapshot, ProposedHouse, PublicNotice


SCHEMA_VERSION = 3


class ProjectRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def migrate(self) -> None:
        with self.connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
                INSERT INTO schema_version(version)
                SELECT 0 WHERE NOT EXISTS (SELECT 1 FROM schema_version);

                CREATE TABLE IF NOT EXISTS project(
                    id TEXT PRIMARY KEY, material_type TEXT NOT NULL DEFAULT 'village_house',
                    status TEXT NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, output_pdf_path TEXT NOT NULL DEFAULT '',
                    output_docx_path TEXT NOT NULL DEFAULT '',
                    last_output_format TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS applicant(
                    project_id TEXT PRIMARY KEY REFERENCES project(id) ON DELETE CASCADE,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS family_member(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL REFERENCES project(id) ON DELETE CASCADE,
                    sort_order INTEGER NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS existing_house(
                    project_id TEXT PRIMARY KEY REFERENCES project(id) ON DELETE CASCADE,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS proposed_house(
                    project_id TEXT PRIMARY KEY REFERENCES project(id) ON DELETE CASCADE,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS public_notice(
                    project_id TEXT PRIMARY KEY REFERENCES project(id) ON DELETE CASCADE,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attachment(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL REFERENCES project(id) ON DELETE CASCADE,
                    material_code TEXT NOT NULL, relative_path TEXT NOT NULL,
                    file_type TEXT NOT NULL, sort_order INTEGER NOT NULL,
                    required INTEGER NOT NULL, included_in_pdf INTEGER NOT NULL,
                    included_in_book INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS generation_run(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL REFERENCES project(id) ON DELETE CASCADE,
                    started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
                    incomplete INTEGER NOT NULL DEFAULT 0, output_pdf_path TEXT NOT NULL DEFAULT '',
                    output_docx_path TEXT NOT NULL DEFAULT '',
                    error_type TEXT NOT NULL DEFAULT ''
                );
                """
            )
            current = int(db.execute("SELECT version FROM schema_version").fetchone()[0])
            if current < 2:
                self._add_column(db, "project", "output_docx_path", "TEXT NOT NULL DEFAULT ''")
                self._add_column(db, "project", "last_output_format", "TEXT NOT NULL DEFAULT ''")
                self._add_column(db, "attachment", "included_in_book", "INTEGER NOT NULL DEFAULT 1")
                self._add_column(db, "generation_run", "output_docx_path", "TEXT NOT NULL DEFAULT ''")
                db.execute("UPDATE attachment SET included_in_book=included_in_pdf")
                db.execute("UPDATE project SET last_output_format='pdf' WHERE output_pdf_path<>'' AND last_output_format=''")
            if current < 3:
                self._add_column(db, "project", "material_type", "TEXT NOT NULL DEFAULT 'village_house'")
                db.execute("UPDATE project SET material_type='village_house' WHERE material_type='' OR material_type IS NULL")
            if current < SCHEMA_VERSION:
                db.execute("UPDATE schema_version SET version=?", (SCHEMA_VERSION,))

    @staticmethod
    def _add_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def create_project(self, material_type: str = "village_house") -> ProjectSnapshot:
        now = datetime.now().isoformat(timespec="seconds")
        snapshot = ProjectSnapshot(id=str(uuid.uuid4()), material_type=material_type, created_at=now, updated_at=now)
        self.save(snapshot)
        return snapshot

    def save(self, snapshot: ProjectSnapshot) -> None:
        snapshot.updated_at = datetime.now().isoformat(timespec="seconds")
        with self.connection() as db:
            db.execute(
                "INSERT INTO project(id,material_type,status,created_at,updated_at,output_pdf_path,output_docx_path,last_output_format) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET material_type=excluded.material_type,status=excluded.status,updated_at=excluded.updated_at,"
                "output_pdf_path=excluded.output_pdf_path,output_docx_path=excluded.output_docx_path,last_output_format=excluded.last_output_format",
                (snapshot.id, snapshot.material_type, snapshot.status, snapshot.created_at, snapshot.updated_at, snapshot.output_pdf_path,
                 snapshot.output_docx_path, snapshot.last_output_format),
            )
            self._upsert_payload(db, "applicant", snapshot.id, asdict(snapshot.applicant))
            self._upsert_payload(db, "existing_house", snapshot.id, asdict(snapshot.existing_house))
            self._upsert_payload(db, "proposed_house", snapshot.id, asdict(snapshot.proposed_house))
            self._upsert_payload(db, "public_notice", snapshot.id, asdict(snapshot.public_notice))
            db.execute("DELETE FROM family_member WHERE project_id=?", (snapshot.id,))
            for index, member in enumerate(snapshot.family_members):
                db.execute(
                    "INSERT INTO family_member(project_id,sort_order,payload) VALUES(?,?,?)",
                    (snapshot.id, index, self._json(asdict(member))),
                )

    @staticmethod
    def _json(payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def _upsert_payload(self, db: sqlite3.Connection, table: str, project_id: str, payload: dict) -> None:
        db.execute(
            f"INSERT INTO {table}(project_id,payload) VALUES(?,?) ON CONFLICT(project_id) DO UPDATE SET payload=excluded.payload",
            (project_id, self._json(payload)),
        )

    def load(self, project_id: str) -> ProjectSnapshot:
        with self.connection() as db:
            project = db.execute("SELECT * FROM project WHERE id=?", (project_id,)).fetchone()
            if project is None:
                raise KeyError(project_id)
            payload = lambda table: json.loads(db.execute(f"SELECT payload FROM {table} WHERE project_id=?", (project_id,)).fetchone()[0])
            members = [FamilyMember(**json.loads(row[0])) for row in db.execute("SELECT payload FROM family_member WHERE project_id=? ORDER BY sort_order", (project_id,))]
            attachments = [Attachment(**dict(row)) for row in db.execute(
                "SELECT id,project_id,material_code,relative_path,file_type,sort_order,required,included_in_book,created_at "
                "FROM attachment WHERE project_id=? ORDER BY material_code,sort_order,id", (project_id,)
            )]
            return ProjectSnapshot(
                id=project["id"], material_type=project["material_type"], status=project["status"], created_at=project["created_at"], updated_at=project["updated_at"],
                output_pdf_path=project["output_pdf_path"], output_docx_path=project["output_docx_path"],
                last_output_format=project["last_output_format"], applicant=Applicant(**payload("applicant")), family_members=members,
                existing_house=ExistingHouse(**payload("existing_house")), proposed_house=ProposedHouse(**payload("proposed_house")),
                public_notice=PublicNotice(**payload("public_notice")), attachments=attachments,
            )

    def list_projects(self, search: str = "", material_type: str = "village_house") -> list[ProjectSnapshot]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT p.id FROM project p JOIN applicant a ON a.project_id=p.id "
                "WHERE p.material_type=? AND (?='' OR json_extract(a.payload,'$.name') LIKE ?) ORDER BY p.updated_at DESC",
                (material_type, search, f"%{search}%"),
            ).fetchall()
        return [self.load(row[0]) for row in rows]

    def add_attachment(self, attachment: Attachment) -> int:
        with self.connection() as db:
            cursor = db.execute(
                "INSERT INTO attachment(project_id,material_code,relative_path,file_type,sort_order,required,included_in_pdf,included_in_book,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (attachment.project_id, attachment.material_code, attachment.relative_path, attachment.file_type, attachment.sort_order,
                 int(attachment.required), int(attachment.included_in_book), int(attachment.included_in_book), attachment.created_at),
            )
            return int(cursor.lastrowid)

    def remove_attachment(self, attachment_id: int) -> None:
        with self.connection() as db:
            db.execute("DELETE FROM attachment WHERE id=?", (attachment_id,))

    def delete_project_record(self, project_id: str) -> None:
        with self.connection() as db:
            db.execute("DELETE FROM project WHERE id=?", (project_id,))

    def start_generation(self, project_id: str, incomplete: bool) -> int:
        with self.connection() as db:
            cursor = db.execute(
                "INSERT INTO generation_run(project_id,started_at,status,incomplete) VALUES(?,?,?,?)",
                (project_id, datetime.now().isoformat(timespec="seconds"), "running", int(incomplete)),
            )
            return int(cursor.lastrowid)

    def finish_generation(
        self,
        run_id: int,
        *,
        output_path: str = "",
        output_format: str = "docx",
        error_type: str = "",
    ) -> None:
        output_column = "output_pdf_path" if output_format == "pdf" else "output_docx_path"
        with self.connection() as db:
            db.execute(
                f"UPDATE generation_run SET finished_at=?,status=?,{output_column}=?,error_type=? WHERE id=?",
                (datetime.now().isoformat(timespec="seconds"), "failed" if error_type else "completed", output_path, error_type, run_id),
            )
