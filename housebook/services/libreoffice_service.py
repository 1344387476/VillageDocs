from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class ConversionError(RuntimeError):
    pass


class LibreOfficeService:
    def __init__(self, soffice: Path) -> None:
        self.soffice = soffice

    def available(self) -> bool:
        return self.soffice.is_file()

    def convert(self, source: Path, output_dir: Path, target: str) -> Path:
        if not self.available():
            raise ConversionError(f"未找到内置 LibreOffice：{self.soffice}")
        output_dir.mkdir(parents=True, exist_ok=True)
        profile = Path(tempfile.mkdtemp(prefix="housebook-lo-"))
        try:
            profile_uri = profile.resolve().as_uri()
            command = [
                str(self.soffice), "--headless", "--nologo", "--nodefault", "--nofirststartwizard",
                f"-env:UserInstallation={profile_uri}", "--convert-to", target, "--outdir", str(output_dir), str(source),
            ]
            environment = os.environ.copy()
            environment["HOME"] = str(profile)
            result = subprocess.run(command, capture_output=True, text=True, timeout=120, env=environment, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            destination = output_dir / f"{source.stem}.{target.split(':', 1)[0]}"
            if result.returncode != 0 or not destination.exists():
                raise ConversionError(f"转换失败：{source.name}（退出码 {result.returncode}）")
            return destination
        except subprocess.TimeoutExpired as exc:
            raise ConversionError(f"转换超时：{source.name}") from exc
        finally:
            shutil.rmtree(profile, ignore_errors=True)

    def to_pdf(self, source: Path, output_dir: Path) -> Path:
        return self.convert(source, output_dir, "pdf")

    def to_docx(self, source: Path, output_dir: Path) -> Path:
        return self.convert(source, output_dir, "docx")

