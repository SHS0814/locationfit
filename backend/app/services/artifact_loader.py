from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import pandas as pd


INDEX_FILE = "area_recommendation_index.parquet"
EVIDENCE_FILE = "area_industry_evidence.parquet"


@dataclass(frozen=True)
class ArtifactBundle:
    recommendation_index: pd.DataFrame
    evidence: pd.DataFrame
    manifest: dict


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_artifacts(artifact_dir: Path) -> ArtifactBundle:
    manifest_path = artifact_dir / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"아티팩트 manifest를 찾을 수 없습니다: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = {name: artifact_dir / name for name in (INDEX_FILE, EVIDENCE_FILE)}
    for name, path in paths.items():
        if not path.exists():
            raise RuntimeError(f"추천 아티팩트를 찾을 수 없습니다: {path}")
        expected = manifest.get("files", {}).get(name, {}).get("sha256")
        if expected and _sha256(path) != expected:
            raise RuntimeError(f"추천 아티팩트 체크섬이 일치하지 않습니다: {name}")

    index = pd.read_parquet(paths[INDEX_FILE])
    evidence = pd.read_parquet(paths[EVIDENCE_FILE])
    index_required = {
        "area_code", "area_name", "district_name", "admin_dong_name",
        "area_type_code", "area_type_name", "latitude", "longitude", "data_reliability",
    }
    evidence_required = {
        "area_code", "industry_code", "industry_name", "data_reliability",
        "reliability_grade", "stale_observation_flag",
    }
    missing_index = sorted(index_required - set(index.columns))
    missing_evidence = sorted(evidence_required - set(evidence.columns))
    if missing_index or missing_evidence:
        raise RuntimeError(
            f"추천 아티팩트 스키마가 올바르지 않습니다. index={missing_index}, evidence={missing_evidence}"
        )
    if not index["latitude"].between(37.0, 38.0).all() or not index["longitude"].between(126.0, 128.0).all():
        raise RuntimeError("추천 아티팩트 좌표가 서울 범위를 벗어났습니다.")
    return ArtifactBundle(index, evidence, manifest)
