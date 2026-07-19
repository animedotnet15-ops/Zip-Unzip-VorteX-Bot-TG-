"""Local filesystem zip/unzip helpers."""
from __future__ import annotations

import os
import re
import uuid
import zipfile
from pathlib import Path

from config import config

WORK_DIR = Path(config.work_dir)
WORK_DIR.mkdir(parents=True, exist_ok=True)


def safe_name(name: str) -> str:
    name = re.sub(r"[^\w\-. ]", "_", name).strip() or "file"
    return name[:120]


def new_task_dir() -> Path:
    d = WORK_DIR / uuid.uuid4().hex
    d.mkdir(parents=True, exist_ok=True)
    return d


def cleanup_dir(d: Path) -> None:
    try:
        for p in sorted(d.glob("**/*"), reverse=True):
            if p.is_file():
                p.unlink(missing_ok=True)
            else:
                p.rmdir()
        d.rmdir()
    except Exception:
        pass


def create_zip(task_dir: Path, ordered_files: list[tuple[Path, str]], zip_name: str) -> Path:
    """ordered_files: list of (local_path, display_name_in_archive) in the desired order."""
    zip_path = task_dir / safe_name(zip_name)
    if not zip_path.suffix == ".zip":
        zip_path = zip_path.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for index, (local_path, display_name) in enumerate(ordered_files, start=1):
            arcname = f"{index:02d}_{safe_name(display_name)}"
            zf.write(local_path, arcname=arcname)
    return zip_path


def extract_zip(zip_path: Path, dest_dir: Path) -> list[Path]:
    extracted = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            zf.extract(info, dest_dir)
            extracted.append(dest_dir / info.filename)
    return extracted
