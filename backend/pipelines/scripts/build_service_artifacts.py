from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from datetime import datetime, timezone

import pandas as pd
from pyproj import Transformer


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_DIR = PROJECT_ROOT / "data/processed"
OUTPUT_DIR = PROJECT_ROOT / "backend/artifacts/current"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    index = pd.read_parquet(SOURCE_DIR / "area_recommendation_index.parquet")
    profile = pd.read_parquet(SOURCE_DIR / "area_profile.parquet")
    latest = (
        profile.sort_values("quarter")
        .groupby("area_code", observed=True, sort=False)
        .tail(1)[["area_code", "admin_dong_name", "x_coord", "y_coord"]]
    )
    transformer = Transformer.from_crs("EPSG:5181", "EPSG:4326", always_xy=True)
    longitude, latitude = transformer.transform(latest["x_coord"].to_numpy(), latest["y_coord"].to_numpy())
    latest = latest.assign(longitude=longitude, latitude=latitude).drop(columns=["x_coord", "y_coord"])
    index = index.merge(latest, on="area_code", how="left", validate="one_to_one")
    if index[["latitude", "longitude"]].isna().any().any():
        raise ValueError("일부 상권의 WGS84 좌표를 생성하지 못했습니다.")

    index_path = OUTPUT_DIR / "area_recommendation_index.parquet"
    evidence_path = OUTPUT_DIR / "area_industry_evidence.parquet"
    index.to_parquet(index_path, index=False)
    shutil.copy2(SOURCE_DIR / "area_industry_evidence.parquet", evidence_path)
    manifest = {
        "artifact_version": "2025q4-v1",
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "coordinate_reference": {"source": "EPSG:5181", "target": "EPSG:4326"},
        "data_period": {"performance": "2021Q1~2025Q4", "profile": "2024Q1~2025Q4"},
        "files": {
            index_path.name: {"rows": len(index), "sha256": sha256(index_path)},
            evidence_path.name: {"rows": len(pd.read_parquet(evidence_path)), "sha256": sha256(evidence_path)},
        },
    }
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
