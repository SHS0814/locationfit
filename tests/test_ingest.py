import pandas as pd
import pytest

from src.data import ingest as ingest_module
from src.data.ingest import stable_frame_digest, validate_preserved_interim


KEYS = ["quarter", "area_code", "industry_code"]


def _sales_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "quarter": pd.Series(["20251", "20251", "20252"], dtype="string"),
        "area_code": pd.Series(["A1", "A2", "A1"], dtype="string"),
        "industry_code": pd.Series(["I1", "I1", "I1"], dtype="string"),
        "sales_krw": [100, 200, 300],
    })


def test_stable_frame_digest_ignores_row_column_order_and_compatible_dtypes() -> None:
    original = _sales_frame()
    reordered = original.iloc[::-1][list(reversed(original.columns))].reset_index(drop=True)
    reordered["sales_krw"] = reordered["sales_krw"].astype("Int64")

    assert stable_frame_digest(original, sort_by=KEYS) == stable_frame_digest(
        reordered,
        sort_by=KEYS,
    )


def test_preserved_interim_accepts_identical_normalized_content() -> None:
    current = _sales_frame()
    existing = current.sample(frac=1, random_state=7).reset_index(drop=True)

    result = validate_preserved_interim(
        "sales",
        existing,
        current,
        keys=KEYS,
        start_quarter="20251",
        end_quarter="20254",
    )

    assert len(result["key_digest"]) == 64
    assert len(result["content_digest"]) == 64


def test_preserved_interim_rejects_duplicate_keys() -> None:
    current = _sales_frame()
    existing = current.copy()
    existing.loc[1, KEYS] = existing.loc[0, KEYS].to_list()

    with pytest.raises(ValueError, match="중복 표준 키"):
        validate_preserved_interim(
            "sales", existing, current, keys=KEYS,
            start_quarter="20251", end_quarter="20254",
        )


def test_preserved_interim_rejects_changed_key_set_with_same_row_count() -> None:
    current = _sales_frame()
    existing = current.copy()
    existing.loc[0, "area_code"] = "CHANGED"

    with pytest.raises(ValueError, match="핵심 키 집합"):
        validate_preserved_interim(
            "sales", existing, current, keys=KEYS,
            start_quarter="20251", end_quarter="20254",
        )


def test_preserved_interim_rejects_changed_value_with_same_keys_and_row_count() -> None:
    current = _sales_frame()
    existing = current.copy()
    existing.loc[0, "sales_krw"] += 1

    with pytest.raises(ValueError, match="interim 값"):
        validate_preserved_interim(
            "sales", existing, current, keys=KEYS,
            start_quarter="20251", end_quarter="20254",
        )


def test_ingest_all_records_digests_for_a_matching_protected_file(tmp_path, monkeypatch) -> None:
    current = _sales_frame()
    current.to_parquet(tmp_path / "sales.parquet", index=False)
    report = {
        "dataset": "sales",
        "source_rows": len(current),
        "period_filtered_rows": len(current),
        "rows_after_exact_dedup": len(current),
        "exact_duplicate_rows_removed": 0,
        "key_duplicate_rows": 0,
        "key_duplicate_cause": "none",
        "area_count": 2,
        "industry_count": 1,
        "quarter_count": 2,
        "quarter_min": "20251",
        "quarter_max": "20252",
    }
    monkeypatch.setattr(
        ingest_module,
        "ingest_dataset",
        lambda *args, **kwargs: (current.copy(), report.copy()),
    )
    config = {
        "analysis_period": {"start_quarter": "20251", "end_quarter": "20254"},
        "datasets": {
            "sales": {
                "folder": "unused",
                "grain": "quarter_area_industry",
                "required": True,
            },
        },
    }

    diagnostics = ingest_module.ingest_all(
        config=config,
        output_dir=tmp_path,
        preserve_existing=("sales",),
    )

    assert diagnostics.loc[0, "write_status"] == "preserved_existing"
    assert len(diagnostics.loc[0, "preserved_key_digest"]) == 64
    assert len(diagnostics.loc[0, "preserved_content_digest"]) == 64
    pd.testing.assert_frame_equal(pd.read_parquet(tmp_path / "sales.parquet"), current)
