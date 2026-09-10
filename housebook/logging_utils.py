from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(log_dir / "housebook.log", encoding="utf-8")],
        force=True,
    )


def safe_event(logger: logging.Logger, event: str, *, project_id: str = "", material_code: str = "", error_type: str = "") -> None:
    logger.info(
        "event=%s project_id=%s material_code=%s error_type=%s",
        event,
        project_id,
        material_code,
        error_type,
    )
