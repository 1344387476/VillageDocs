from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document
from PIL import Image

from housebook.services.attachment_service import AttachmentService
from housebook.services.generation_service import GenerationService
from housebook.services.libreoffice_service import LibreOfficeService
from housebook.services.pdf_service import PdfService
from housebook.services.project_service import ProjectService
from housebook.services.template_service import TemplateService
from tests.test_real_templates import ROOT, TEMPLATES, fictional_project


SOFFICE = ROOT / "runtime" / "libreoffice" / "program" / "soffice.exe"


@pytest.mark.skipif(not SOFFICE.exists(), reason="需要内置 LibreOffice")
def test_application_form_stays_on_one_page(tmp_path: Path) -> None:
    templates = TemplateService(TEMPLATES)
    generated_docx = templates.render("01", fictional_project(), tmp_path / "docx")
    generated_pdf = LibreOfficeService(SOFFICE).to_pdf(generated_docx, tmp_path / "pdf")
    assert PdfService().validate(generated_pdf) == 1


@pytest.mark.skipif(not SOFFICE.exists(), reason="需要内置 LibreOffice")
def test_complete_generation_pipeline_supports_word_and_pdf(tmp_path: Path) -> None:
    projects = ProjectService(tmp_path / "workspace")
    attachments = AttachmentService(projects)
    templates = TemplateService(TEMPLATES)
    converter = LibreOfficeService(SOFFICE)
    generation = GenerationService(projects, templates, attachments, converter)

    created = projects.create_project()
    project = fictional_project()
    project.id = created.id
    project.created_at = created.created_at
    projects.repository.save(project)

    image = tmp_path / "fixture.jpg"
    Image.new("RGB", (1000, 700), "white").save(image)
    for code in ("08", "09", "10", "13", "14", "11", "11"):
        attachments.add(project.id, code, image)

    word_output = generation.generate(project.id, output_format="docx")
    assert word_output.exists()
    assert word_output.parent == projects.root
    assert word_output.suffix == ".docx"
    assert "未完整" not in word_output.name
    Document(word_output)

    pdf_output = generation.generate(project.id, output_format="pdf")
    assert pdf_output.exists()
    assert pdf_output.parent == projects.root
    assert pdf_output.suffix == ".pdf"
    assert PdfService().validate(pdf_output) >= 10
    reloaded = projects.repository.load(project.id)
    assert reloaded.status == "completed"
    assert reloaded.output_docx_path.endswith(".docx")
    assert reloaded.output_pdf_path.endswith(".pdf")
    assert reloaded.last_output_format == "pdf"
