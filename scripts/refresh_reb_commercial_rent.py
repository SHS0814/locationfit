#!/usr/bin/env python3
"""Manually refresh static REB commercial-rent artifacts.

Usage:
    REB_API_KEY=... .venv/bin/python scripts/refresh_reb_commercial_rent.py

The key is used only for this process and is never written to disk or logs.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any

import pandas as pd

from src.data.reb_api import RebGisClient, RebOpenApiClient


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config/reb_commercial_rent.json"
DEFAULT_ARTIFACT_DIR = ROOT / "backend/artifacts/current"
DEFAULT_INDEX = DEFAULT_ARTIFACT_DIR / "area_recommendation_index.parquet"


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


def _quarter(value: object) -> str:
    raw = str(value)
    if len(raw) != 6 or raw[4] != "0" or raw[-1] not in "1234":
        raise ValueError(f"알 수 없는 REB 분기 코드입니다: {raw}")
    return f"{raw[:4]}Q{raw[-1]}"


def _previous_period(value: str) -> str:
    year, quarter = int(value[:4]), int(value[-1])
    if quarter == 1:
        return f"{year - 1}04"
    return f"{year}0{quarter - 1}"


def _path(row: pd.Series) -> str:
    return _first_text(row, "GRP_FULLNM", "CLS_FULLNM")


def _market_name(row: pd.Series) -> str:
    return _first_text(row, "GRP_NM", "CLS_NM")


def _first_text(row: pd.Series, *columns: str) -> str:
    for column in columns:
        value = row.get(column)
        if pd.notna(value) and str(value).strip():
            return str(value).strip()
    return ""


def _seoul_market_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    paths = frame.apply(_path, axis=1)
    frame = frame.loc[paths.str.startswith("서울>") & paths.str.count(">>").eq(0)].copy()
    frame["survey_area_name"] = frame.apply(_market_name, axis=1)
    frame["reference_period"] = frame["WRTTIME_IDTFR_ID"].map(_quarter)
    frame["value"] = pd.to_numeric(frame["DTA_VAL"], errors="coerce")
    return frame.loc[frame["value"].notna() & frame["survey_area_name"].ne("")]


def build_observations(
    downloaded: dict[str, dict[str, list[dict[str, Any]]]],
    floor_codes: dict[str, str],
) -> pd.DataFrame:
    all_types: list[pd.DataFrame] = []
    for property_type, tables in downloaded.items():
        floor = _seoul_market_rows(tables["floor_rent"])
        floor["floor"] = floor["CLS_NM"].astype(str).str.replace(" ", "").map(
            {key.replace(" ", ""): value for key, value in floor_codes.items()}
        )
        floor["item"] = floor["ITM_NM"].astype(str)
        rents = floor.loc[floor["item"].str.contains("임대료", na=False) & floor["floor"].notna()].copy()
        rents["unit_converted_rent_krw_sqm"] = rents["value"] * 1000.0
        rents["source_priority"] = 0

        utility = floor.loc[floor["item"].str.contains("효용", na=False) & floor["floor"].notna(), [
            "survey_area_name", "reference_period", "floor", "value",
        ]].rename(columns={"value": "floor_utility_ratio"})
        if not utility.empty and utility["floor_utility_ratio"].median() > 2:
            utility["floor_utility_ratio"] /= 100.0

        regional = _seoul_market_rows(tables["regional_rent"])
        regional = regional.loc[regional["ITM_NM"].astype(str).str.contains("임대료", na=False)].copy()
        regional["floor"] = "f1"
        regional["unit_converted_rent_krw_sqm"] = regional["value"] * 1000.0
        regional["source_priority"] = 1
        rents = pd.concat([rents, regional], ignore_index=True)
        rents = rents.sort_values([
            "survey_area_name", "reference_period", "floor", "source_priority",
        ]).drop_duplicates(
            ["survey_area_name", "reference_period", "floor"], keep="first"
        )
        if not utility.empty:
            rents = rents.merge(
                utility,
                on=["survey_area_name", "reference_period", "floor"],
                how="left",
                validate="one_to_one",
            )
        else:
            rents["floor_utility_ratio"] = pd.NA

        rates = _seoul_market_rows(tables["conversion_rate"])
        rates = rates.loc[rates["ITM_NM"].astype(str).str.contains("전환율", na=False), [
            "survey_area_name", "reference_period", "value",
        ]].rename(columns={"value": "annual_conversion_rate"})
        rates["annual_conversion_rate"] /= 100.0
        rents = rents.merge(
            rates,
            on=["survey_area_name", "reference_period"],
            how="left",
            validate="many_to_one",
        )
        period_fallback = rates.groupby("reference_period", as_index=False)["annual_conversion_rate"].median()
        rents = rents.merge(period_fallback, on="reference_period", how="left", suffixes=("", "_fallback"))
        rents["annual_conversion_rate"] = rents["annual_conversion_rate"].fillna(
            rents["annual_conversion_rate_fallback"]
        )
        rents["property_type"] = property_type
        all_types.append(rents[[
            "property_type", "survey_area_name", "floor", "reference_period",
            "unit_converted_rent_krw_sqm", "floor_utility_ratio", "annual_conversion_rate",
        ]])
    observations = pd.concat(all_types, ignore_index=True)
    observations = observations.dropna(subset=["annual_conversion_rate"])
    observations = observations.loc[
        observations["unit_converted_rent_krw_sqm"].gt(0)
        & observations["annual_conversion_rate"].gt(0)
    ].copy()
    observations = observations.sort_values(
        ["property_type", "survey_area_name", "reference_period", "floor"]
    ).reset_index(drop=True)
    if observations.empty:
        raise ValueError("유효한 서울 상가 임대료 관측치를 만들지 못했습니다.")
    return observations


def _normalize_name(value: object) -> str:
    return "".join(str(value).split()).replace("/", "").replace("·", "")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth = 6371.0088
    first, second = math.radians(lat1), math.radians(lat2)
    dlat = second - first
    dlon = math.radians(lon2 - lon1)
    value = math.sin(dlat / 2) ** 2 + math.cos(first) * math.cos(second) * math.sin(dlon / 2) ** 2
    return 2 * earth * math.asin(math.sqrt(value))


def build_crosswalk(
    area_index: pd.DataFrame,
    observations: pd.DataFrame,
    gis_rows: dict[str, list[dict[str, Any]]],
) -> pd.DataFrame:
    output: list[dict[str, object]] = []
    for property_type, source_rows in gis_rows.items():
        valid_markets = set(observations.loc[
            observations["property_type"].eq(property_type), "survey_area_name"
        ].astype(str))
        canonical = {_normalize_name(name): name for name in valid_markets}
        centers: list[tuple[str, float, float]] = []
        for row in source_rows:
            normalized = _normalize_name(row.get("secNm", ""))
            if normalized not in canonical:
                continue
            try:
                centers.append((canonical[normalized], float(row["y"]), float(row["x"])))
            except (KeyError, TypeError, ValueError):
                continue
        centers = list({(name, lat, lon) for name, lat, lon in centers})
        if not centers:
            raise ValueError(f"{property_type}의 서울 REB 표본상권 좌표를 찾지 못했습니다.")
        for area in area_index.itertuples(index=False):
            nearest = min(
                centers,
                key=lambda center: _haversine_km(
                    float(area.latitude), float(area.longitude), center[1], center[2]
                ),
            )
            output.append({
                "area_code": str(area.area_code),
                "property_type": property_type,
                "survey_area_name": nearest[0],
                "distance_km": _haversine_km(
                    float(area.latitude), float(area.longitude), nearest[1], nearest[2]
                ),
                "mapping_method": "nearest_reb_survey_market",
            })
    crosswalk = pd.DataFrame(output).sort_values(["area_code", "property_type"]).reset_index(drop=True)
    expected = len(area_index) * len(gis_rows)
    if len(crosswalk) != expected or crosswalk.duplicated(["area_code", "property_type"]).any():
        raise ValueError(f"상가 비용 crosswalk coverage 오류: expected={expected}, actual={len(crosswalk)}")
    return crosswalk


def main() -> None:
    parser = argparse.ArgumentParser(description="REB 상가 임대료 정적 아티팩트 수동 갱신")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--area-index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data/raw/reb_commercial_rent")
    parser.add_argument(
        "--from-raw",
        type=Path,
        help="이미 내려받은 키 없는 원본 디렉터리를 재가공하고 네트워크 수집을 건너뜁니다.",
    )
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    downloaded: dict[str, dict[str, list[dict[str, Any]]]] = {}
    if args.from_raw:
        raw_target = args.from_raw.resolve()
        meta = json.loads((raw_target / "download_meta.json").read_text(encoding="utf-8"))
        latest_period = str(meta["latest_period"])
        for property_type in config["property_types"]:
            downloaded[property_type] = {
                role: json.loads((raw_target / f"{property_type}_{role}.json").read_text(encoding="utf-8"))
                for role in ("regional_rent", "floor_rent", "conversion_rate")
            }
        all_gis_rows = [
            row
            for source_type in config["property_types"]
            for row in json.loads(
                (raw_target / f"{source_type}_gis_centers.json").read_text(encoding="utf-8")
            )
        ]
        gis_rows = {
            property_type: [
                row for row in all_gis_rows
                if str(row.get("buldGbn")) == str(item["gis_building_code"])
            ]
            for property_type, item in config["property_types"].items()
        }
        if any(not rows for rows in gis_rows.values()):
            raise ValueError("원본 GIS 중심점에 설정된 상가 유형 코드가 없습니다.")
    else:
        api_key = os.getenv("REB_API_KEY", "").strip()
        if not api_key:
            raise SystemExit("REB_API_KEY가 필요합니다. 키는 갱신 프로세스에서만 사용됩니다.")
        client = RebOpenApiClient(api_key=api_key, base_url=config["api_url"])
        table_meta: dict[str, object] = {}
        for property_type, item in config["property_types"].items():
            downloaded[property_type] = {}
            for role in ("regional_rent", "floor_rent", "conversion_rate"):
                table_id = item[f"{role}_table"]
                rows = client.fetch_table(table_id, cycle=config["cycle"])
                downloaded[property_type][role] = rows
                table_meta[table_id] = {"property_type": property_type, "role": role, "rows": len(rows)}

        periods = sorted({str(row["WRTTIME_IDTFR_ID"]) for tables in downloaded.values() for rows in tables.values() for row in rows})
        latest_period = periods[-1]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        raw_target = args.raw_dir / stamp
        for property_type, tables in downloaded.items():
            for role, rows in tables.items():
                _atomic_json(raw_target / f"{property_type}_{role}.json", rows)

        gis = RebGisClient(base_url=config["gis_url"])
        gis_rows = {
            property_type: gis.fetch_seoul_centers(
                period=latest_period,
                previous_period=_previous_period(latest_period),
                building_code=str(item["gis_building_code"]),
            )
            for property_type, item in config["property_types"].items()
        }
        for property_type, rows in gis_rows.items():
            _atomic_json(raw_target / f"{property_type}_gis_centers.json", rows)
        _atomic_json(raw_target / "download_meta.json", {
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "source": "한국부동산원 R-ONE",
            "api_url": config["api_url"],
            "gis_url": config["gis_url"],
            "latest_period": latest_period,
            "tables": table_meta,
            "api_key_recorded": False,
        })

    observations = build_observations(downloaded, config["floor_codes"])
    crosswalk = build_crosswalk(pd.read_parquet(args.area_index), observations, gis_rows)
    observation_path = args.artifact_dir / "commercial_rent_observations.parquet"
    crosswalk_path = args.artifact_dir / "commercial_rent_crosswalk.parquet"
    _atomic_parquet(observation_path, observations)
    _atomic_parquet(crosswalk_path, crosswalk)

    manifest_path = args.artifact_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for path, frame in ((observation_path, observations), (crosswalk_path, crosswalk)):
        manifest.setdefault("files", {})[path.name] = {"rows": len(frame), "sha256": _sha256(path)}
    manifest.setdefault("data_period", {})["commercial_rent"] = _quarter(latest_period)
    manifest["commercial_rent_source"] = "한국부동산원 R-ONE 상업용부동산 임대동향조사"
    _atomic_json(manifest_path, manifest)
    print(f"완료: observations={len(observations)}, crosswalk={len(crosswalk)}, period={_quarter(latest_period)}")


if __name__ == "__main__":
    main()
