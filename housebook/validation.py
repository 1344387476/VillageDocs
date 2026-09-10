from __future__ import annotations

import re
from dataclasses import dataclass

from .models import ProjectSnapshot


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    field: str
    message: str


_ID_18 = re.compile(r"^\d{17}[0-9Xx]$")
_ID_15 = re.compile(r"^\d{15}$")
_PHONE = re.compile(r"^1\d{10}$")


def valid_chinese_id(value: str) -> bool:
    value = value.strip()
    if _ID_15.fullmatch(value):
        return True
    if not _ID_18.fullmatch(value):
        return False
    weights = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    checks = "10X98765432"
    return checks[sum(int(digit) * weight for digit, weight in zip(value[:17], weights)) % 11] == value[-1].upper()


def validate_snapshot(snapshot: ProjectSnapshot) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    applicant = snapshot.applicant
    house = snapshot.proposed_house
    if not applicant.name.strip():
        issues.append(ValidationIssue("applicant.name", "申请人姓名不能为空"))
    if not applicant.id_number.strip():
        issues.append(ValidationIssue("applicant.id_number", "身份证号不能为空"))
    elif not valid_chinese_id(applicant.id_number):
        issues.append(ValidationIssue("applicant.id_number", "身份证号格式或校验位不正确"))
    if applicant.phone and not _PHONE.fullmatch(applicant.phone.strip()):
        issues.append(ValidationIssue("applicant.phone", "手机号应为 11 位"))
    if applicant.household_population is None or applicant.household_population < 1:
        issues.append(ValidationIssue("applicant.household_population", "家庭人口必须大于等于 1"))
    if not house.address.strip():
        issues.append(ValidationIssue("house.address", "拟建地址不能为空"))
    for field_name in ("homestead_area", "footprint_area", "building_area", "length", "width", "height"):
        value = getattr(house, field_name)
        if value is not None and value <= 0:
            issues.append(ValidationIssue(f"house.{field_name}", "数值必须大于 0"))
    if house.floors is not None and house.floors <= 0:
        issues.append(ValidationIssue("house.floors", "建筑层数必须大于 0"))
    return issues

