from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .paths import default_workspace_root


@dataclass(slots=True)
class AppSettings:
    workspace_root: str = ""

    @property
    def workspace(self) -> Path:
        return Path(self.workspace_root) if self.workspace_root else default_workspace_root()


class SettingsStore:
    def __init__(self, config_path: Path | None = None) -> None:
        self.path = config_path or (Path.home() / "AppData" / "Local" / "VillageDocs" / "settings.json")

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return AppSettings(workspace_root=str(payload.get("workspace_root", "")))
        except (OSError, ValueError, TypeError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
