from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


def village_committee_name(value: str) -> str:
    """Return the full legal village committee name without duplicated suffixes."""
    name = value.strip()
    if not name:
        return ""
    for suffix in ("村村民委员会", "村民委员会", "村委会"):
        if name.endswith(suffix):
            name = name[: -len(suffix)].rstrip()
            break
    if not name.endswith("村"):
        name += "村"
    return f"{name}村民委员会"


def town_government_name(value: str) -> str:
    """Return the full township government name without duplicated suffixes."""
    name = value.strip()
    if not name:
        return ""
    if name.endswith("人民政府"):
        return name
    if name.endswith("镇政府") or name.endswith("乡政府"):
        name = name[:-2]
    return f"{name}人民政府"


@dataclass(slots=True)
class Applicant:
    name: str = ""
    gender: str = ""
    age: int | None = None
    id_number: str = ""
    phone: str = ""
    household_location: str = ""
    town: str = ""
    administrative_village: str = ""
    natural_village: str = ""
    group_name: str = ""
    household_population: int | None = None


@dataclass(slots=True)
class FamilyMember:
    name: str = ""
    age: int | None = None
    relation: str = ""
    id_number: str = ""
    household_location: str = ""


@dataclass(slots=True)
class ExistingHouse:
    homestead_area: float | None = None
    building_area: float | None = None
    ownership_certificate_no: str = ""
    disposal_type: str = ""
    disposal_area: float | None = None


@dataclass(slots=True)
class ProposedHouse:
    build_type: str = ""
    application_reason: str = ""
    address: str = ""
    homestead_area: float | None = None
    footprint_area: float | None = None
    building_area: float | None = None
    length: float | None = None
    width: float | None = None
    floors: int | None = None
    height: float | None = None
    roof_type: str = ""
    land_type: str = ""
    east_boundary: str = ""
    south_boundary: str = ""
    west_boundary: str = ""
    north_boundary: str = ""
    neighbor_opinions_requested: bool | None = None


@dataclass(slots=True)
class PublicNotice:
    village_name: str = ""
    contact_person: str = ""
    contact_phone: str = ""
    notice_date: str = ""
    auto_fill_date: bool = False


@dataclass(slots=True)
class Attachment:
    id: int | None = None
    project_id: str = ""
    material_code: str = ""
    relative_path: str = ""
    file_type: str = ""
    sort_order: int = 0
    required: bool = True
    included_in_book: bool = True
    created_at: str = ""


@dataclass(slots=True)
class ProjectSnapshot:
    id: str
    material_type: str = "village_house"
    status: str = "draft"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    output_pdf_path: str = ""
    output_docx_path: str = ""
    last_output_format: str = ""
    applicant: Applicant = field(default_factory=Applicant)
    family_members: list[FamilyMember] = field(default_factory=list)
    existing_house: ExistingHouse = field(default_factory=ExistingHouse)
    proposed_house: ProposedHouse = field(default_factory=ProposedHouse)
    public_notice: PublicNotice = field(default_factory=PublicNotice)
    attachments: list[Attachment] = field(default_factory=list)

    def field_context(self) -> dict[str, Any]:
        applicant = asdict(self.applicant)
        applicant["village_committee_name"] = village_committee_name(self.applicant.administrative_village)
        applicant["town_government_name"] = town_government_name(self.applicant.town)
        public_notice = asdict(self.public_notice)
        public_notice["village_committee_name"] = village_committee_name(
            self.public_notice.village_name or self.applicant.administrative_village
        )
        context: dict[str, Any] = {
            "project": {"id": self.id, "status": self.status},
            "applicant": applicant,
            "family_members": [asdict(member) for member in self.family_members],
            "existing_house": asdict(self.existing_house),
            "house": asdict(self.proposed_house),
            "public_notice": public_notice,
        }
        return context
