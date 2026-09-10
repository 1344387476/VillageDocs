from housebook.models import ProjectSnapshot
from housebook.validation import valid_chinese_id, validate_snapshot


def test_chinese_id_checksum() -> None:
    assert valid_chinese_id("11010519491231002X")
    assert not valid_chinese_id("110105194912310021")


def test_required_project_fields() -> None:
    project = ProjectSnapshot(id="test-project")
    fields = {issue.field for issue in validate_snapshot(project)}
    assert "applicant.name" in fields
    assert "applicant.id_number" in fields
    assert "applicant.household_population" in fields
    assert "house.address" in fields


def test_valid_fictional_project() -> None:
    project = ProjectSnapshot(id="test-project")
    project.applicant.name = "测试甲"
    project.applicant.id_number = "11010519491231002X"
    project.applicant.household_population = 3
    project.proposed_house.address = "测试村一组虚构地址"
    assert validate_snapshot(project) == []

