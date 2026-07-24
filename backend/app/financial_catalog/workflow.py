from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Literal

from sqlalchemy.orm import Session

from backend.app.financial_catalog.bizinfo import BizinfoClient, merge_bizinfo_items
from backend.app.financial_catalog.contracts import CatalogBundle
from backend.app.financial_catalog.loader import catalog_digest, load_curated_catalog
from backend.app.financial_catalog.persistence import (
    apply_bundle,
    bundle_from_database,
    database_digest,
    lock_catalog,
)
from backend.app.financial_catalog.validation import validate_catalog


SourceSelection = Literal["curated", "bizinfo", "all"]


def preview_catalog(
    session: Session,
    *,
    curated_root: Path,
    output_root: Path,
    source: SourceSelection,
    bizinfo_api_key: str = "",
    now: datetime | None = None,
    bizinfo_items: list[dict[str, Any]] | None = None,
) -> Path:
    checked_at = now or datetime.now(UTC)
    bundle = load_curated_catalog(curated_root)
    raw_items: list[dict[str, Any]] = []
    include_bizinfo = source in {"bizinfo", "all"}
    if include_bizinfo:
        raw_items = (
            bizinfo_items
            if bizinfo_items is not None
            else BizinfoClient(bizinfo_api_key).fetch_financial_announcements()
        )
        bundle = merge_bizinfo_items(bundle, raw_items, checked_at=checked_at)

    report = validate_catalog(bundle, now=checked_at)
    current = bundle_from_database(session)
    diff = _catalog_diff(current, bundle, close_missing_bizinfo=include_bizinfo)
    stamp = checked_at.strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_root / stamp
    if run_dir.exists():
        raise FileExistsError(f"동일 실행 디렉터리가 이미 있습니다: {run_dir}")
    run_dir.mkdir(parents=True)

    catalog_payload = bundle.model_dump(mode="json")
    _atomic_json(run_dir / "catalog.json", catalog_payload)
    _atomic_json(run_dir / "diff.json", diff)
    _atomic_json(run_dir / "validation.json", {
        **report.model_dump(mode="json"),
        "error_count": report.error_count,
        "warning_count": report.warning_count,
    })
    if include_bizinfo:
        _atomic_json(run_dir / "bizinfo_raw.json", raw_items)
    manifest = {
        "manifest_version": 1,
        "generated_at": checked_at.isoformat(),
        "source_selection": source,
        "catalog_sha256": _json_hash(catalog_payload),
        "base_database_sha256": catalog_digest(current),
        "error_count": report.error_count,
        "warning_count": report.warning_count,
        "product_count": len(bundle.products),
    }
    _atomic_json(run_dir / "manifest.json", manifest)
    return run_dir


def apply_preview(
    session: Session,
    run_dir: Path,
    *,
    accept_warnings: bool = False,
) -> dict[str, int]:
    lock_catalog(session)
    manifest = _read_json(run_dir / "manifest.json")
    catalog_payload = _read_json(run_dir / "catalog.json")
    if manifest.get("catalog_sha256") != _json_hash(catalog_payload):
        raise ValueError("preview catalog 해시가 manifest와 일치하지 않습니다.")
    if int(manifest.get("error_count", 0)):
        raise ValueError("검증 오류가 있는 preview는 반영할 수 없습니다.")
    if int(manifest.get("warning_count", 0)) and not accept_warnings:
        raise ValueError("검증 경고가 있습니다. 검토 후 --accept-warnings를 지정해주세요.")
    current_digest = database_digest(session)
    if current_digest != manifest.get("base_database_sha256"):
        raise ValueError("preview 이후 DB 카탈로그가 변경되었습니다. preview를 다시 생성해주세요.")
    bundle = CatalogBundle.model_validate(catalog_payload)
    generated_at = datetime.fromisoformat(str(manifest["generated_at"]))
    result = apply_bundle(
        session,
        bundle,
        close_expired_bizinfo=manifest.get("source_selection") in {"bizinfo", "all"},
        as_of=generated_at.date(),
    )
    return result


def _catalog_diff(
    current: CatalogBundle,
    desired: CatalogBundle,
    *,
    close_missing_bizinfo: bool,
) -> dict[str, Any]:
    current_products = {item.slug: item.model_dump(mode="json") for item in current.products}
    desired_products = {item.slug: item.model_dump(mode="json") for item in desired.products}
    added = sorted(set(desired_products) - set(current_products))
    updated: list[dict[str, Any]] = []
    unchanged: list[str] = []
    for slug in sorted(set(desired_products) & set(current_products)):
        fields = sorted(
            key for key in desired_products[slug]
            if desired_products[slug][key] != current_products[slug].get(key)
        )
        if fields:
            updated.append({"slug": slug, "fields": fields})
        else:
            unchanged.append(slug)
    close_candidates = sorted(
        item.slug for item in current.products
        if close_missing_bizinfo
        and item.status.value != "closed"
        and item.slug not in desired_products
        and item.extra_data.get("curation_level") == "api_metadata_only"
        and any(source.data_source_key == "bizinfo-api" for source in item.sources)
    )
    return {
        "added": added,
        "updated": updated,
        "unchanged": unchanged,
        "close_candidates": close_candidates,
        "counts": {
            "added": len(added),
            "updated": len(updated),
            "unchanged": len(unchanged),
            "close_candidates": len(close_candidates),
        },
    }


def _json_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        temp = Path(stream.name)
    temp.replace(path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
