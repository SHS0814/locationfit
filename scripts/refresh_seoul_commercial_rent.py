#!/usr/bin/env python3
"""Manually refresh static Seoul commercial-rent artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.data.seoul_rent_api import SeoulRentClient

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIR = ROOT / "backend/artifacts/current"
DEFAULT_AREA_FILE = ROOT / "data/raw/area/area.csv"
AREA_TYPES = ("A", "D", "R", "U")
SOURCE_NAME = "서울시 상권분석서비스 임대시세(서울신용보증재단 보증 고객 통계)"
FLOOR_COLUMNS = {
    "all": "TOT_FLOOR",
    "f1": "FST_FLOOR",
    "non_f1": "EX_FLOOR",
}


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        temp = Path(stream.name)
    temp.chmod(0o644)
    temp.replace(path)


def _atomic_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".parquet", delete=False) as stream:
        temp = Path(stream.name)
    try:
        frame.to_parquet(temp, index=False)
        temp.chmod(0o644)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_name(value: object) -> str:
    return unicodedata.normalize("NFC", str(value)).replace("·", ".").strip()


def _source_area_name(value: object) -> str:
    text = str(value).strip()
    return text.rsplit(" (", 1)[0] if " (" in text else text


def _numeric(value: object) -> float | None:
    text = str(value).replace(",", "").strip()
    if not text:
        return None
    number = pd.to_numeric(text, errors="coerce")
    if pd.isna(number) or float(number) <= 0:
        return None
    return float(number)


def load_area_reference(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str)
    required = {
        "TRDAR_SE_CD", "TRDAR_CD", "TRDAR_CD_NM", "ADSTRD_CD", "ADSTRD_CD_NM",
        "SIGNGU_CD", "SIGNGU_CD_NM",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"서울 상권 기준 파일 컬럼이 부족합니다: {missing}")
    output = frame[list(required)].rename(columns={
        "TRDAR_SE_CD": "area_type_code",
        "TRDAR_CD": "area_code",
        "TRDAR_CD_NM": "area_name",
        "ADSTRD_CD": "admin_dong_code",
        "ADSTRD_CD_NM": "admin_dong_name",
        "SIGNGU_CD": "district_code",
        "SIGNGU_CD_NM": "district_name",
    })
    output["match_name"] = output["area_name"].map(_normalize_name)
    if output.duplicated(["area_type_code", "match_name"]).any():
        raise ValueError("서울 상권 기준 파일에 상권유형/상권명 중복이 있습니다.")
    return output


def build_observations(
    source_rows: dict[str, list[dict[str, Any]]],
    area_reference: pd.DataFrame,
    *,
    year: int,
    quarter: int,
) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for area_type in AREA_TYPES:
        expected = area_reference.loc[area_reference["area_type_code"].eq(area_type)].copy()
        rows = [row for row in source_rows.get(area_type, []) if row.get("GUBUN") == "dong"]
        district_lookup = {
            _normalize_name(row.get("NM", "")): row
            for row in source_rows.get(area_type, [])
            if row.get("GUBUN") == "gu"
        }
        lookup: dict[str, dict[str, Any]] = {}
        for row in rows:
            name = _normalize_name(_source_area_name(row.get("NM", "")))
            if not name or name in lookup:
                raise ValueError(f"서울시 임대시세 {area_type} 응답에 빈 이름 또는 중복 상권이 있습니다: {name}")
            lookup[name] = row
        expected_names = set(expected["match_name"])
        source_names = set(lookup)
        if expected_names != source_names:
            raise ValueError(
                f"서울시 임대시세 {area_type} 상권 매칭 오류: "
                f"missing={sorted(expected_names - source_names)[:10]}, "
                f"unexpected={sorted(source_names - expected_names)[:10]}"
            )
        for area in expected.itertuples(index=False):
            row = lookup[str(area.match_name)]
            basis_geography = "admin_dong"
            basis_name = str(area.admin_dong_name)
            if not any(_numeric(row.get(f"{prefix}_TOT_FLOOR")) for prefix in ("BF1", "BF2", "BF3")):
                district_name = _normalize_name(area.district_name)
                if district_name not in district_lookup:
                    raise ValueError(f"서울시 임대시세 자치구 대체값이 없습니다: {area.district_name}")
                row = district_lookup[district_name]
                basis_geography = "district"
                basis_name = str(area.district_name)
            for offset, prefix in ((-2, "BF1"), (-1, "BF2"), (0, "BF3")):
                reference_period = f"{year + offset}Q{quarter}"
                for floor, suffix in FLOOR_COLUMNS.items():
                    source_value = _numeric(row.get(f"{prefix}_{suffix}"))
                    if source_value is None:
                        continue
                    records.append({
                        "area_code": str(area.area_code),
                        "area_name": str(area.area_name),
                        "admin_dong_code": str(area.admin_dong_code),
                        "admin_dong_name": str(area.admin_dong_name),
                        "rent_basis_geography": basis_geography,
                        "rent_basis_name": basis_name,
                        "area_type_code": area_type,
                        "reference_period": reference_period,
                        "floor": floor,
                        "source_unit_rent_krw_per_3_3sqm": source_value,
                        "unit_converted_rent_krw_sqm": source_value / 3.3,
                        "annual_conversion_rate": 0.12,
                    })
    observations = pd.DataFrame(records).sort_values(
        ["area_code", "reference_period", "floor"]
    ).reset_index(drop=True)
    latest = f"{year}Q{quarter}"
    latest_all = observations.loc[
        observations["reference_period"].eq(latest) & observations["floor"].eq("all"),
        "area_code",
    ].nunique()
    if latest_all != area_reference["area_code"].nunique():
        raise ValueError("서울시 최신 전체층 임대시세와 자치구 대체값이 모든 상권을 포함하지 않습니다.")
    if observations.duplicated(["area_code", "reference_period", "floor"]).any():
        raise ValueError("서울시 임대시세 관측치에 area/period/floor 중복이 있습니다.")
    return observations


def main() -> None:
    parser = argparse.ArgumentParser(description="서울시 상권분석서비스 임대시세 정적 아티팩트 갱신")
    parser.add_argument("--year", type=int)
    parser.add_argument("--quarter", type=int, choices=(1, 2, 3, 4))
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--area-file", type=Path, default=DEFAULT_AREA_FILE)
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data/raw/seoul_commercial_rent")
    parser.add_argument("--from-raw", type=Path)
    args = parser.parse_args()

    if bool(args.year) != bool(args.quarter):
        parser.error("--year와 --quarter는 함께 지정해야 합니다.")

    if args.from_raw:
        raw_target = args.from_raw.resolve()
        meta = json.loads((raw_target / "download_meta.json").read_text(encoding="utf-8"))
        year, quarter = int(meta["year"]), int(meta["quarter"])
        source_rows = {
            code: json.loads((raw_target / f"rent_{code}.json").read_text(encoding="utf-8"))
            for code in AREA_TYPES
        }
    else:
        client = SeoulRentClient()
        if args.year and args.quarter:
            year, quarter = args.year, args.quarter
        else:
            year, quarter = client.available_periods()[0]
        source_rows = {
            code: client.rental_rows(year=year, quarter=quarter, area_type_code=code)
            for code in AREA_TYPES
        }
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        raw_target = args.raw_dir / stamp
        for code, rows in source_rows.items():
            _atomic_json(raw_target / f"rent_{code}.json", rows)
        _atomic_json(raw_target / "download_meta.json", {
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "source": SOURCE_NAME,
            "base_url": "https://golmok.seoul.go.kr",
            "year": year,
            "quarter": quarter,
            "area_type_rows": {code: len(rows) for code, rows in source_rows.items()},
        })

    area_reference = load_area_reference(args.area_file)
    observations = build_observations(
        source_rows, area_reference, year=year, quarter=quarter
    )
    observation_path = args.artifact_dir / "commercial_rent_observations.parquet"
    _atomic_parquet(observation_path, observations)

    manifest_path = args.artifact_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_version"] = "2025q4-v3"
    manifest["schema_version"] = 4
    manifest["created_at"] = datetime.now(timezone.utc).isoformat()
    manifest.setdefault("files", {}).pop("commercial_rent_crosswalk.parquet", None)
    manifest["files"][observation_path.name] = {
        "rows": len(observations),
        "sha256": _sha256(observation_path),
    }
    manifest.setdefault("data_period", {})["commercial_rent"] = f"{year}Q{quarter}"
    manifest["commercial_rent_source"] = SOURCE_NAME
    _atomic_json(manifest_path, manifest)

    crosswalk_path = args.artifact_dir / "commercial_rent_crosswalk.parquet"
    crosswalk_path.unlink(missing_ok=True)
    print(
        f"완료: observations={len(observations)}, areas={observations['area_code'].nunique()}, "
        f"period={year}Q{quarter}"
    )


if __name__ == "__main__":
    main()
