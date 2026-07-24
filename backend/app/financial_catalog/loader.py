from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from backend.app.financial_catalog.contracts import CatalogBundle, CatalogDocument


def _merge_unique(items: list, key: str, label: str) -> list:
    output: dict[str, object] = {}
    for item in items:
        value = str(getattr(item, key))
        if value in output:
            raise ValueError(f"중복 {label}: {value}")
        output[value] = item
    return list(output.values())


def load_curated_catalog(root: Path) -> CatalogBundle:
    if not root.exists():
        raise FileNotFoundError(f"금융지원 카탈로그 디렉터리가 없습니다: {root}")
    documents: list[CatalogDocument] = []
    for path in sorted((*root.rglob("*.yaml"), *root.rglob("*.yml"))):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if raw is None:
            continue
        try:
            documents.append(CatalogDocument.model_validate(raw))
        except Exception as exc:
            raise ValueError(f"검수 카탈로그 형식 오류: {path}: {exc}") from exc

    organizations = _merge_unique(
        [item for document in documents for item in document.organizations],
        "code",
        "기관 코드",
    )
    data_sources = _merge_unique(
        [item for document in documents for item in document.data_sources],
        "key",
        "출처 키",
    )
    products = _merge_unique(
        [item for document in documents for item in document.products],
        "slug",
        "상품 slug",
    )
    aliases = [item for document in documents for item in document.source_aliases]
    alias_keys: set[tuple[str, str]] = set()
    for alias in aliases:
        alias_key = (alias.data_source_key, alias.external_id)
        if alias_key in alias_keys:
            raise ValueError(f"중복 출처 별칭: {alias_key}")
        alias_keys.add(alias_key)
    return CatalogBundle(
        organizations=organizations,
        data_sources=data_sources,
        products=products,
        source_aliases=aliases,
    )


def catalog_json(bundle: CatalogBundle) -> str:
    return json.dumps(
        bundle.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def catalog_digest(bundle: CatalogBundle) -> str:
    return hashlib.sha256(catalog_json(bundle).encode("utf-8")).hexdigest()
