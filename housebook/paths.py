from __future__ import annotations

import os
import sys
from pathlib import Path


def package_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def install_root() -> Path:
    """Return the writable directory beside the installed executable."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    return package_root().joinpath("resources", *parts)


def libreoffice_path() -> Path:
    configured = os.environ.get("HOUSEBOOK_SOFFICE")
    if configured:
        return Path(configured)
    return package_root() / "runtime" / "libreoffice" / "program" / "soffice.exe"


def default_workspace_root() -> Path:
    return install_root() / "resource"
