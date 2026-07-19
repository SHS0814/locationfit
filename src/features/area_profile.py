"""Build the recent-quarter commercial-area structural feature panel."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from src.data.config import generate_quarters, load_datasets_config
from src.utils.paths import INTERIM_DIR, OUTPUT_DIR, PROCESSED_DIR, PROJECT_ROOT


KEYS = ["quarter", "area_code"]
CORE_BLOCKS = ["floating_population", "resident_population", "worker_population", "stores"]
SUPPLEMENTAL_BLOCKS = ["facilities", "apartments", "commercial_change"]
MODEL_EXCLUDE = {
    "quarter",
    "area_code",
    "area_name",
    "area_type_code",
    "area_type_name",
    "district_code",
    "district_name",
    "admin_dong_code",
    "admin_dong_name",
    "commercial_change_code",
    "commercial_change_name",
    "x_coord",
    "y_coord",
}


@dataclass(frozen=True)
class AreaProfileResult:
    """In-memory outputs produced by :func:`build_area_profile`."""

    profile: pd.DataFrame
    feature_dictionary: pd.DataFrame
    validation: pd.DataFrame
    merge_report: pd.DataFrame


def safe_ratio(
    numerator: pd.Series,
    denominator: pd.Series,
    *,
    default: float = 0.0,
) -> pd.Series:
    """Divide aligned series without producing infinities for zero denominators."""
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce")
    result = pd.Series(default, index=num.index, dtype="float64")
    valid = num.notna() & den.notna() & den.ne(0)
    result.loc[valid] = num.loc[valid] / den.loc[valid]
    return result.replace([np.inf, -np.inf], default)


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], dataset: str) -> None:
    missing = [column for column in columns if column not in frame]
    if missing:
        raise ValueError(f"[{dataset}] 필요한 컬럼이 없습니다: {missing}")


def _filter_period(frame: pd.DataFrame, quarters: list[str], dataset: str) -> pd.DataFrame:
    _require_columns(frame, KEYS, dataset)
    filtered = frame.loc[frame["quarter"].astype("string").isin(quarters)].copy()
    filtered["quarter"] = filtered["quarter"].astype("string")
    filtered["area_code"] = filtered["area_code"].astype("string")
    if filtered.empty:
        raise ValueError(f"[{dataset}] 프로필 기간 데이터가 없습니다: {quarters[0]}~{quarters[-1]}")
    return filtered


def _ensure_unique(frame: pd.DataFrame, dataset: str) -> None:
    duplicates = int(frame.duplicated(KEYS, keep=False).sum())
    if duplicates:
        raise ValueError(f"[{dataset}] quarter × area_code 중복 행: {duplicates:,}")


def _density_log(value: pd.Series, area_size: pd.Series) -> pd.Series:
    density = safe_ratio(value * 1_000_000.0, area_size)
    return np.log1p(density.clip(lower=0))


def build_area_base(area: pd.DataFrame, quarters: list[str]) -> pd.DataFrame:
    """Cross the unique area master with configured profile quarters."""
    rename = {
        "TRDAR_SE_CD": "area_type_code",
        "TRDAR_SE_CD_NM": "area_type_name",
        "SIGNGU_CD": "district_code",
        "SIGNGU_CD_NM": "district_name",
        "ADSTRD_CD": "admin_dong_code",
        "ADSTRD_CD_NM": "admin_dong_name",
        "XCNTS_VALUE": "x_coord",
        "YDNTS_VALUE": "y_coord",
        "RELM_AR": "area_size_sqm",
    }
    _require_columns(area, ["area_code", "area_name", *rename], "area")
    master = area[["area_code", "area_name", *rename]].rename(columns=rename).copy()
    master["area_code"] = master["area_code"].astype("string")
    for code in ("area_type_code", "district_code", "admin_dong_code"):
        master[code] = master[code].astype("string")
    if master["area_code"].duplicated().any():
        raise ValueError("[area] area_code가 고유하지 않습니다.")
    if master["area_size_sqm"].isna().any() or master["area_size_sqm"].le(0).any():
        raise ValueError("[area] 상권 면적이 없거나 0 이하인 행이 있습니다.")
    quarter_frame = pd.DataFrame({"quarter": pd.Series(quarters, dtype="string")})
    base = quarter_frame.merge(master, how="cross")
    for code in ("A", "D", "R", "U"):
        base[f"area_type_{code.lower()}"] = base["area_type_code"].eq(code).astype("int8")
    return base.sort_values(KEYS).reset_index(drop=True)


def build_floating_features(frame: pd.DataFrame, area: pd.DataFrame) -> pd.DataFrame:
    """Create floating-population density and composition features."""
    columns = {
        "TOT_FLPOP_CO": "floating_population",
        "ML_FLPOP_CO": "male_floating_ratio",
        "FML_FLPOP_CO": "female_floating_ratio",
        "AGRDE_10_FLPOP_CO": "age_10_floating_ratio",
        "AGRDE_20_FLPOP_CO": "age_20_floating_ratio",
        "AGRDE_30_FLPOP_CO": "age_30_floating_ratio",
        "AGRDE_40_FLPOP_CO": "age_40_floating_ratio",
        "AGRDE_50_FLPOP_CO": "age_50_floating_ratio",
        "AGRDE_60_ABOVE_FLPOP_CO": "age_60_plus_floating_ratio",
        "TMZON_00_06_FLPOP_CO": "time_00_06_floating_ratio",
        "TMZON_06_11_FLPOP_CO": "time_06_11_floating_ratio",
        "TMZON_11_14_FLPOP_CO": "time_11_14_floating_ratio",
        "TMZON_14_17_FLPOP_CO": "time_14_17_floating_ratio",
        "TMZON_17_21_FLPOP_CO": "time_17_21_floating_ratio",
        "TMZON_21_24_FLPOP_CO": "time_21_24_floating_ratio",
    }
    day_columns = ["MON_FLPOP_CO", "TUES_FLPOP_CO", "WED_FLPOP_CO", "THUR_FLPOP_CO", "FRI_FLPOP_CO", "SAT_FLPOP_CO", "SUN_FLPOP_CO"]
    _require_columns(frame, [*KEYS, *columns, *day_columns], "floating_population")
    result = frame[KEYS].copy()
    total = frame["TOT_FLPOP_CO"]
    result["floating_population"] = total
    for source, target in list(columns.items())[1:]:
        result[target] = safe_ratio(frame[source], total)
    day_total = frame[day_columns].sum(axis=1, min_count=1)
    result["weekend_floating_ratio"] = safe_ratio(frame["SAT_FLPOP_CO"] + frame["SUN_FLPOP_CO"], day_total)
    result = result.merge(area[["area_code", "area_size_sqm"]], on="area_code", how="left", validate="many_to_one")
    result["log_floating_density"] = _density_log(result["floating_population"], result["area_size_sqm"])
    return result.drop(columns="area_size_sqm")


def build_resident_features(frame: pd.DataFrame, area: pd.DataFrame) -> pd.DataFrame:
    """Create resident density and household-structure features."""
    needed = [*KEYS, "TOT_REPOP_CO", "TOT_HSHLD_CO"]
    _require_columns(frame, needed, "resident_population")
    result = frame[KEYS].copy()
    result["resident_population"] = frame["TOT_REPOP_CO"]
    result["average_household_size"] = safe_ratio(frame["TOT_REPOP_CO"], frame["TOT_HSHLD_CO"])
    result = result.merge(area[["area_code", "area_size_sqm"]], on="area_code", how="left", validate="many_to_one")
    result["log_resident_density"] = _density_log(result["resident_population"], result["area_size_sqm"])
    return result.drop(columns="area_size_sqm")


def build_worker_features(frame: pd.DataFrame, area: pd.DataFrame) -> pd.DataFrame:
    """Create worker-population density features."""
    _require_columns(frame, [*KEYS, "TOT_WRC_POPLTN_CO"], "worker_population")
    result = frame[KEYS].copy()
    result["worker_population"] = frame["TOT_WRC_POPLTN_CO"]
    result = result.merge(area[["area_code", "area_size_sqm"]], on="area_code", how="left", validate="many_to_one")
    result["log_worker_density"] = _density_log(result["worker_population"], result["area_size_sqm"])
    return result.drop(columns="area_size_sqm")


def build_apartment_features(frame: pd.DataFrame, area: pd.DataFrame) -> pd.DataFrame:
    """Create apartment supply, size, and representative-price features."""
    size_columns = [
        "AE_66_SQMT_BELO_HSHLD_CO",
        "AE_66_SQMT_HSHLD_CO",
        "AE_99_SQMT_HSHLD_CO",
        "AE_132_SQMT_HSHLD_CO",
        "AE_165_SQMT_HSHLD_CO",
    ]
    _require_columns(frame, [*KEYS, "APT_HSMP_CO", *size_columns, "AVRG_AE", "AVRG_MKTC"], "apartments")
    result = frame[KEYS].copy()
    households = frame[size_columns].sum(axis=1, min_count=1)
    result["apartment_complex_count"] = frame["APT_HSMP_CO"]
    result["apartment_household_count"] = households
    result["apartment_average_area"] = frame["AVRG_AE"]
    result["apartment_average_market_price"] = frame["AVRG_MKTC"]
    result["log_apartment_market_price"] = np.log1p(frame["AVRG_MKTC"].clip(lower=0))
    result["small_apartment_household_ratio"] = safe_ratio(frame["AE_66_SQMT_BELO_HSHLD_CO"], households)
    medium_large = frame[["AE_99_SQMT_HSHLD_CO", "AE_132_SQMT_HSHLD_CO", "AE_165_SQMT_HSHLD_CO"]].sum(axis=1, min_count=1)
    result["medium_large_apartment_household_ratio"] = safe_ratio(medium_large, households)
    result = result.merge(area[["area_code", "area_size_sqm"]], on="area_code", how="left", validate="many_to_one")
    result["log_apartment_complex_density"] = _density_log(result["apartment_complex_count"], result["area_size_sqm"])
    result["log_apartment_household_density"] = _density_log(result["apartment_household_count"], result["area_size_sqm"])
    return result.drop(columns="area_size_sqm")


def build_facility_features(frame: pd.DataFrame, area: pd.DataFrame) -> pd.DataFrame:
    """Create total and grouped attraction-facility density/ratio features."""
    groups = {
        "transport": ["ARPRT_CO", "RLROAD_STATN_CO", "BUS_TRMINL_CO", "SUBWAY_STATN_CO", "BUS_STTN_CO"],
        "education": ["KNDRGR_CO", "ELESCH_CO", "MSKUL_CO", "HGSCHL_CO", "UNIV_CO"],
        "medical": ["GEHSPT_CO", "GNRL_HSPTL_CO", "PARMACY_CO"],
        "shopping": ["DRTS_CO", "SUPMK_CO"],
        "culture": ["THEAT_CO"],
    }
    needed = [*KEYS, "VIATR_FCLTY_CO", *(column for columns in groups.values() for column in columns)]
    _require_columns(frame, needed, "facilities")
    result = frame[KEYS].copy()
    result["facility_count"] = frame["VIATR_FCLTY_CO"]
    for group, columns in groups.items():
        result[f"{group}_facility_count"] = frame[columns].sum(axis=1, min_count=1)
        result[f"{group}_facility_ratio"] = safe_ratio(result[f"{group}_facility_count"], result["facility_count"])
    result = result.merge(area[["area_code", "area_size_sqm"]], on="area_code", how="left", validate="many_to_one")
    result["log_facility_density"] = _density_log(result["facility_count"], result["area_size_sqm"])
    for group in groups:
        result[f"log_{group}_facility_density"] = _density_log(result[f"{group}_facility_count"], result["area_size_sqm"])
    return result.drop(columns="area_size_sqm")


def build_store_features(frame: pd.DataFrame, *, smoothing_strength: float = 20.0) -> pd.DataFrame:
    """Aggregate industry rows and smooth rates toward citywide priors."""
    needed = [*KEYS, "industry_code", "SIMILR_INDUTY_STOR_CO", "FRC_STOR_CO", "OPBIZ_RT", "CLSBIZ_RT"]
    _require_columns(frame, needed, "stores")
    work = frame[needed].copy()
    for column in ("SIMILR_INDUTY_STOR_CO", "FRC_STOR_CO", "OPBIZ_RT", "CLSBIZ_RT"):
        work[column] = pd.to_numeric(work[column], errors="coerce").fillna(0.0).clip(lower=0)
    work["weighted_open"] = work["SIMILR_INDUTY_STOR_CO"] * work["OPBIZ_RT"].clip(upper=100) / 100.0
    work["weighted_close"] = work["SIMILR_INDUTY_STOR_CO"] * work["CLSBIZ_RT"].clip(upper=100) / 100.0
    positive = work["SIMILR_INDUTY_STOR_CO"].gt(0)
    work["active"] = positive.astype("int8")
    work["n_log_n"] = 0.0
    work.loc[positive, "n_log_n"] = (
        work.loc[positive, "SIMILR_INDUTY_STOR_CO"]
        * np.log(work.loc[positive, "SIMILR_INDUTY_STOR_CO"])
    )
    grouped = work.groupby(KEYS, sort=False, observed=True).agg(
        store_count=("SIMILR_INDUTY_STOR_CO", "sum"),
        franchise_store_count=("FRC_STOR_CO", "sum"),
        active_industry_count=("active", "sum"),
        weighted_open=("weighted_open", "sum"),
        weighted_close=("weighted_close", "sum"),
        n_log_n=("n_log_n", "sum"),
    ).reset_index()
    total = grouped["store_count"]
    active = grouped["active_industry_count"]
    entropy = pd.Series(0.0, index=grouped.index)
    valid = total.gt(0) & active.gt(1)
    entropy.loc[valid] = (
        np.log(total.loc[valid]) - grouped.loc[valid, "n_log_n"] / total.loc[valid]
    ) / np.log(active.loc[valid])
    total_city_stores = float(total.sum())
    franchise_prior = float(grouped["franchise_store_count"].sum() / total_city_stores) if total_city_stores else 0.0
    opening_prior = float(grouped["weighted_open"].sum() / total_city_stores) if total_city_stores else 0.0
    closing_prior = float(grouped["weighted_close"].sum() / total_city_stores) if total_city_stores else 0.0
    diversity_prior = float(entropy.median())
    denominator = total + smoothing_strength
    grouped["store_smoothing_weight"] = safe_ratio(total, denominator)
    grouped["industry_diversity"] = safe_ratio(total * entropy + smoothing_strength * diversity_prior, denominator)
    grouped["franchise_ratio"] = safe_ratio(grouped["franchise_store_count"] + smoothing_strength * franchise_prior, denominator)
    grouped["opening_rate"] = safe_ratio(grouped["weighted_open"] + smoothing_strength * opening_prior, denominator)
    grouped["closing_rate"] = safe_ratio(grouped["weighted_close"] + smoothing_strength * closing_prior, denominator)
    grouped["net_store_growth_rate"] = grouped["opening_rate"] - grouped["closing_rate"]
    return grouped.drop(columns=["weighted_open", "weighted_close", "n_log_n"])


def build_commercial_change_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Create commercial-change duration and one-hot state features."""
    rename = {
        "TRDAR_CHNGE_IX": "commercial_change_code",
        "TRDAR_CHNGE_IX_NM": "commercial_change_name",
        "OPR_SALE_MT_AVRG": "local_open_months_average",
        "CLS_SALE_MT_AVRG": "local_close_months_average",
        "SU_OPR_SALE_MT_AVRG": "seoul_open_months_average",
        "SU_CLS_SALE_MT_AVRG": "seoul_close_months_average",
    }
    _require_columns(frame, [*KEYS, *rename], "commercial_change")
    result = frame[[*KEYS, *rename]].rename(columns=rename).copy()
    for code in ("LL", "LH", "HL", "HH"):
        result[f"commercial_change_{code.lower()}"] = result["commercial_change_code"].eq(code).astype("int8")
    return result


def _merge_block(
    base: pd.DataFrame,
    block: pd.DataFrame,
    name: str,
    source_rows: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    _ensure_unique(block, name)
    observed_column = f"{name}_observed"
    block = block.copy()
    block[observed_column] = 1
    before = len(base)
    merged = base.merge(block, on=KEYS, how="left", validate="one_to_one")
    observed = merged[observed_column].fillna(0).astype("int8")
    merged[observed_column] = observed
    feature_columns = [column for column in block if column not in {*KEYS, observed_column}]
    string_columns = [column for column in feature_columns if block[column].dtype.kind in {"O", "U", "S"} or isinstance(block[column].dtype, pd.StringDtype)]
    numeric_columns = [column for column in feature_columns if column not in string_columns]
    merged[numeric_columns] = merged[numeric_columns].fillna(0.0)
    for column in string_columns:
        merged[column] = merged[column].fillna("unknown").astype("string")
    matched = int(observed.sum())
    report = {
        "dataset": name,
        "source_rows": source_rows,
        "aggregated_rows": len(block),
        "duplicate_key_rows": 0,
        "base_rows_before": before,
        "rows_after_merge": len(merged),
        "matched_rows": matched,
        "missing_rows": before - matched,
        "join_rate": matched / before if before else 0.0,
        "missing_reason": "no source row for quarter × area_code; Seoul API omits zero/unreported areas",
        "fill_policy": "numeric zero, categorical unknown, observed flag retained",
    }
    return merged, report


def winsorize_features(
    frame: pd.DataFrame,
    columns: Iterable[str],
    *,
    lower_quantile: float = 0.005,
    upper_quantile: float = 0.995,
) -> tuple[pd.DataFrame, dict[str, tuple[float, float]]]:
    """Clip selected continuous features and return the applied bounds."""
    result = frame.copy()
    bounds: dict[str, tuple[float, float]] = {}
    for column in columns:
        if column not in result or not pd.api.types.is_numeric_dtype(result[column]):
            continue
        lower = float(result[column].quantile(lower_quantile))
        upper = float(result[column].quantile(upper_quantile))
        if np.isfinite(lower) and np.isfinite(upper) and lower < upper:
            result[column] = result[column].clip(lower=lower, upper=upper)
            bounds[column] = (lower, upper)
    return result, bounds


def _source_for_feature(column: str) -> str:
    if "floating" in column:
        return "floating_population"
    if "resident" in column or "household_size" in column:
        return "resident_population"
    if "worker" in column:
        return "worker_population"
    if "apartment" in column:
        return "apartments"
    if "facility" in column:
        return "facilities"
    if column in {"store_count", "franchise_store_count", "active_industry_count", "industry_diversity", "franchise_ratio", "opening_rate", "closing_rate", "net_store_growth_rate", "store_smoothing_weight", "log_store_density"}:
        return "stores"
    if column.startswith("commercial_") or column.endswith("months_average"):
        return "commercial_change"
    if column in {"area_size_sqm", "x_coord", "y_coord"} or column.startswith(("area_", "district_", "admin_dong_")):
        return "area"
    return "derived"


def build_feature_dictionary(
    profile: pd.DataFrame,
    bounds: dict[str, tuple[float, float]],
) -> pd.DataFrame:
    """Describe every output column, its source, transformation, and missing policy."""
    rows: list[dict[str, Any]] = []
    for column in profile.columns:
        source = _source_for_feature(column)
        if column in KEYS:
            role, group, description = "key", "key", "quarter × commercial-area canonical key"
        elif column in MODEL_EXCLUDE:
            role, group, description = "metadata", "area", "area master or categorical metadata"
        elif column.endswith("_observed"):
            role, group, description = "quality", "reliability", "1 when a source row was observed for the key"
        elif column in {"observation_count", "observed_block_count", "data_reliability"}:
            role, group, description = "quality", "reliability", "source coverage and longitudinal reliability indicator"
        else:
            role = "feature"
            group = source
            description = "derived structural feature"
        formula = "source value"
        if column.startswith("log_"):
            formula = "log1p(value per square kilometre) or log1p(price)"
        elif column in {"opening_rate", "closing_rate", "franchise_ratio", "industry_diversity"}:
            formula = "empirical-Bayes smoothing with 20-store citywide prior"
        elif column.endswith("_ratio") or column.endswith("_rate") or column.endswith("_balance"):
            formula = "safe ratio; zero denominator returns 0"
        lower, upper = bounds.get(column, (np.nan, np.nan))
        rows.append({
            "feature": column,
            "group": group,
            "source": source,
            "role": role,
            "dtype": str(profile[column].dtype),
            "description": description,
            "formula": formula,
            "missing_policy": "zero/unknown with source observed flag" if source not in {"area", "derived"} else "not applicable or derived from observed flags",
            "winsor_lower": lower,
            "winsor_upper": upper,
        })
    return pd.DataFrame(rows)


def build_validation_report(
    profile: pd.DataFrame,
    quarters: list[str],
    feature_columns: list[str],
    expected_rows: int,
) -> pd.DataFrame:
    """Create global validation checks plus numeric feature distribution summaries."""
    numeric = profile[feature_columns].select_dtypes(include="number")
    duplicate_rows = int(profile.duplicated(KEYS, keep=False).sum())
    inf_count = int(np.isinf(numeric.to_numpy(dtype=float)).sum())
    actual_quarters = sorted(profile["quarter"].dropna().unique().tolist())
    checks = [
        ("grain_duplicate_rows", duplicate_rows, "PASS" if duplicate_rows == 0 else "FAIL", "quarter × area_code"),
        ("row_count", len(profile), "PASS" if len(profile) == expected_rows else "FAIL", f"expected={expected_rows}"),
        ("quarter_count", len(actual_quarters), "PASS" if actual_quarters == quarters else "FAIL", f"actual={actual_quarters}"),
        ("infinite_value_count", inf_count, "PASS" if inf_count == 0 else "FAIL", "numeric model features"),
        ("overall_feature_missing_rate", float(profile[feature_columns].isna().mean().mean()), "PASS", "after explicit block fill"),
        ("observation_count_min", int(profile["observation_count"].min()), "INFO", "core blocks across 8 quarters"),
        ("observation_count_max", int(profile["observation_count"].max()), "INFO", "core blocks across 8 quarters"),
        ("data_reliability_min", float(profile["data_reliability"].min()), "INFO", "range 0~1"),
        ("data_reliability_mean", float(profile["data_reliability"].mean()), "INFO", "range 0~1"),
        ("historical_compatibility_scope", 2024, "INFO", "2023→2024 warning acknowledged; output uses 20241 and later only"),
    ]
    rows: list[dict[str, Any]] = [
        {"record_type": "global_check", "name": name, "status": status, "value": value, "details": details}
        for name, value, status, details in checks
    ]
    for column in numeric.columns:
        series = numeric[column]
        description = series.describe(percentiles=[0.05, 0.5, 0.95])
        unique_count = int(series.nunique(dropna=True))
        rows.append({
            "record_type": "feature_summary",
            "name": column,
            "status": "WARNING" if unique_count <= 1 else "PASS",
            "value": np.nan,
            "details": "constant feature" if unique_count <= 1 else "",
            "count": int(series.notna().sum()),
            "missing_count": int(series.isna().sum()),
            "missing_rate": float(series.isna().mean()),
            "inf_count": int(np.isinf(series.to_numpy(dtype=float)).sum()),
            "unique_count": unique_count,
            "mean": float(description.get("mean", np.nan)),
            "std": float(description.get("std", np.nan)),
            "min": float(description.get("min", np.nan)),
            "p05": float(description.get("5%", np.nan)),
            "median": float(description.get("50%", np.nan)),
            "p95": float(description.get("95%", np.nan)),
            "max": float(description.get("max", np.nan)),
        })
    return pd.DataFrame(rows)


def build_area_profile(
    *,
    project_root: Path = PROJECT_ROOT,
    interim_dir: Path | None = None,
    processed_dir: Path | None = None,
    output_dir: Path | None = None,
    smoothing_strength: float = 20.0,
) -> AreaProfileResult:
    """Build, validate, and save the 2024Q1~2025Q4 area-profile panel."""
    config = load_datasets_config(project_root / "config/datasets.yaml")
    period = config["area_profile_period"]
    quarters = [str(value) for value in generate_quarters(period["start_quarter"], period["end_quarter"])]
    if quarters != ["20241", "20242", "20243", "20244", "20251", "20252", "20253", "20254"]:
        raise ValueError(f"area_profile_period는 정확히 20241~20254여야 합니다: {quarters}")
    interim = interim_dir or (project_root / "data/interim" if project_root != PROJECT_ROOT else INTERIM_DIR)
    processed = processed_dir or (project_root / "data/processed" if project_root != PROJECT_ROOT else PROCESSED_DIR)
    tables = output_dir or (project_root / "outputs/tables" if project_root != PROJECT_ROOT else OUTPUT_DIR / "tables")
    input_names = ["area", "floating_population", "resident_population", "worker_population", "facilities", "apartments", "stores", "commercial_change"]
    frames: dict[str, pd.DataFrame] = {}
    for name in input_names:
        path = interim / f"{name}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"[{name}] interim 파일이 없습니다: {path}")
        frames[name] = pd.read_parquet(path)
    area_master = frames["area"].copy()
    base = build_area_base(area_master, quarters)
    area_sizes = base[["area_code", "area_size_sqm"]].drop_duplicates("area_code")
    filtered = {name: _filter_period(frames[name], quarters, name) for name in input_names if name != "area"}
    blocks = {
        "floating_population": build_floating_features(filtered["floating_population"], area_sizes),
        "resident_population": build_resident_features(filtered["resident_population"], area_sizes),
        "worker_population": build_worker_features(filtered["worker_population"], area_sizes),
        "facilities": build_facility_features(filtered["facilities"], area_sizes),
        "apartments": build_apartment_features(filtered["apartments"], area_sizes),
        "stores": build_store_features(filtered["stores"], smoothing_strength=smoothing_strength),
        "commercial_change": build_commercial_change_features(filtered["commercial_change"]),
    }
    profile = base
    merge_rows: list[dict[str, Any]] = []
    for name, block in blocks.items():
        profile, report = _merge_block(profile, block, name, len(filtered[name]))
        merge_rows.append(report)
    profile["log_store_density"] = _density_log(profile["store_count"], profile["area_size_sqm"])
    profile["worker_resident_balance"] = safe_ratio(
        profile["worker_population"] - profile["resident_population"],
        profile["worker_population"] + profile["resident_population"],
    )
    core_flags = [f"{name}_observed" for name in CORE_BLOCKS]
    supplemental_flags = [f"{name}_observed" for name in SUPPLEMENTAL_BLOCKS]
    profile["observed_block_count"] = profile[core_flags + supplemental_flags].sum(axis=1).astype("int8")
    profile["core_quarter_observed"] = profile[core_flags].min(axis=1).astype("int8")
    profile["observation_count"] = profile.groupby("area_code", observed=True)["core_quarter_observed"].transform("sum").astype("int8")
    core_fraction = profile[core_flags].mean(axis=1)
    supplemental_fraction = profile[supplemental_flags].mean(axis=1)
    history_fraction = profile["observation_count"] / len(quarters)
    profile["data_reliability"] = (0.5 * core_fraction + 0.2 * supplemental_fraction + 0.3 * history_fraction).clip(0, 1)
    profile = profile.drop(columns="core_quarter_observed")
    clip_columns = [
        "log_floating_density", "log_resident_density", "log_worker_density",
        "average_household_size", "apartment_average_area", "apartment_average_market_price",
        "log_apartment_market_price", "log_apartment_complex_density", "log_apartment_household_density",
        "log_facility_density", "log_transport_facility_density", "log_education_facility_density",
        "log_medical_facility_density", "log_shopping_facility_density", "log_culture_facility_density",
        "log_store_density", "local_open_months_average", "local_close_months_average",
    ]
    profile, bounds = winsorize_features(profile, clip_columns)
    profile["quarter"] = profile["quarter"].astype("string")
    profile["area_code"] = profile["area_code"].astype("string")
    profile = profile.sort_values(KEYS).reset_index(drop=True)
    _ensure_unique(profile, "area_profile")
    feature_columns = [column for column in profile.columns if column not in MODEL_EXCLUDE and column not in KEYS]
    dictionary = build_feature_dictionary(profile, bounds)
    validation = build_validation_report(profile, quarters, feature_columns, len(area_master) * len(quarters))
    merge_report = pd.DataFrame(merge_rows)
    failed_checks = validation.loc[(validation["record_type"] == "global_check") & (validation["status"] == "FAIL")]
    if not failed_checks.empty:
        raise ValueError(f"area profile 검증 실패: {failed_checks[['name', 'details']].to_dict('records')}")
    processed.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    profile.to_parquet(processed / "area_profile.parquet", index=False)
    dictionary.to_csv(tables / "area_profile_feature_dictionary.csv", index=False, encoding="utf-8-sig")
    validation.to_csv(tables / "area_profile_validation.csv", index=False, encoding="utf-8-sig")
    merge_report.to_csv(tables / "area_profile_merge_report.csv", index=False, encoding="utf-8-sig")
    return AreaProfileResult(profile, dictionary, validation, merge_report)
