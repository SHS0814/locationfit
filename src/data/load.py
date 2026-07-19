from __future__ import annotations
from pathlib import Path
import zipfile
import pandas as pd

SUPPORTED_SUFFIXES = {".csv", ".parquet", ".xlsx", ".xls"}

def discover_files(folder: Path) -> list[Path]:
    """Discover supported tabular files recursively, excluding metadata files."""
    if not folder.exists():
        return []
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES)

def read_csv_robust(path: Path, **kwargs) -> pd.DataFrame:
    """Read CSV using the encodings commonly used by Seoul data files."""
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, encoding=encoding, low_memory=False, **kwargs)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"지원 인코딩으로 읽지 못했습니다: {path}") from last_error


def detect_csv_encoding(path: Path) -> str:
    """Return the first supported encoding able to decode a CSV header."""
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            pd.read_csv(path, encoding=encoding, nrows=0)
            return encoding
        except UnicodeDecodeError:
            continue
    raise ValueError(f"지원 인코딩으로 읽지 못했습니다: {path}")

def read_table(path: Path) -> pd.DataFrame:
    """Read one supported CSV, parquet or Excel file."""
    suffix = path.suffix.lower()
    if suffix == ".csv": return read_csv_robust(path)
    if suffix == ".parquet": return pd.read_parquet(path)
    if suffix in {".xlsx", ".xls"}: return pd.read_excel(path)
    raise ValueError(f"지원하지 않는 파일 형식입니다: {path}")

def read_folder(folder: Path) -> pd.DataFrame:
    """Read every supported file in a folder and retain its source filename."""
    files = discover_files(folder)
    if not files:
        raise FileNotFoundError(f"데이터 파일이 없습니다: {folder}")
    frames = []
    for path in files:
        frame = read_table(path)
        frame["_source_file"] = path.name
        frames.append(frame)
    return pd.concat(frames, ignore_index=True, sort=False)


def extract_zip_archives(folder: Path) -> list[Path]:
    """Safely extract ZIP archives below a folder without deleting originals."""
    extracted: list[Path] = []
    for archive in sorted(folder.rglob("*.zip")):
        target = archive.parent / archive.stem
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as zip_file:
            for member in zip_file.infolist():
                destination = (target / member.filename).resolve()
                if target.resolve() not in destination.parents and destination != target.resolve():
                    raise ValueError(f"안전하지 않은 ZIP 경로: {archive} -> {member.filename}")
            zip_file.extractall(target)
        extracted.append(target)
    return extracted
