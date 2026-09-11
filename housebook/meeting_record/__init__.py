"""Meeting-record PDF generation domain."""

from .generation_service import MeetingRecordGenerationService
from .template_config import MeetingTemplateRegistry

__all__ = ["MeetingRecordGenerationService", "MeetingTemplateRegistry"]
