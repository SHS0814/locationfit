"""Tests for area-profile feature engineering helpers."""

import unittest

import numpy as np
import pandas as pd

from src.features.area_profile import (
    build_area_base,
    build_commercial_change_features,
    build_store_features,
    safe_ratio,
    winsorize_features,
)


class AreaProfileFeatureTests(unittest.TestCase):
    def test_safe_ratio_handles_zero_and_missing_denominators(self) -> None:
        result = safe_ratio(pd.Series([4.0, 2.0, 1.0]), pd.Series([2.0, 0.0, np.nan]))
        self.assertEqual(result.tolist(), [2.0, 0.0, 0.0])
        self.assertFalse(np.isinf(result).any())

    def test_area_base_has_complete_unique_quarter_area_panel(self) -> None:
        area = pd.DataFrame(
            {
                "area_code": ["1", "2"],
                "area_name": ["a", "b"],
                "TRDAR_SE_CD": ["A", "R"],
                "TRDAR_SE_CD_NM": ["골목상권", "전통시장"],
                "SIGNGU_CD": ["11", "11"],
                "SIGNGU_CD_NM": ["구", "구"],
                "ADSTRD_CD": ["111", "112"],
                "ADSTRD_CD_NM": ["동1", "동2"],
                "XCNTS_VALUE": [1, 2],
                "YDNTS_VALUE": [3, 4],
                "RELM_AR": [100.0, 200.0],
            }
        )
        result = build_area_base(area, ["20241", "20242"])
        self.assertEqual(len(result), 4)
        self.assertEqual(result.duplicated(["quarter", "area_code"]).sum(), 0)
        self.assertTrue(result["area_code"].map(lambda value: isinstance(value, str)).all())

    def test_store_features_are_unique_and_smoothed(self) -> None:
        frame = pd.DataFrame(
            {
                "quarter": ["20241", "20241", "20241"],
                "area_code": ["1", "1", "2"],
                "industry_code": ["a", "b", "a"],
                "SIMILR_INDUTY_STOR_CO": [8.0, 2.0, 1.0],
                "FRC_STOR_CO": [2.0, 0.0, 0.0],
                "OPBIZ_RT": [10.0, 20.0, 0.0],
                "CLSBIZ_RT": [5.0, 10.0, 0.0],
            }
        )
        result = build_store_features(frame, smoothing_strength=20.0)
        self.assertEqual(len(result), 2)
        self.assertEqual(result.duplicated(["quarter", "area_code"]).sum(), 0)
        for column in ("franchise_ratio", "opening_rate", "closing_rate", "industry_diversity"):
            self.assertTrue(result[column].between(0, 1).all())
        small = result.loc[result["area_code"].eq("2"), "store_smoothing_weight"].iloc[0]
        self.assertAlmostEqual(small, 1 / 21)

    def test_commercial_change_creates_four_state_flags(self) -> None:
        frame = pd.DataFrame(
            {
                "quarter": ["20241"],
                "area_code": ["1"],
                "TRDAR_CHNGE_IX": ["LH"],
                "TRDAR_CHNGE_IX_NM": ["상권확장"],
                "OPR_SALE_MT_AVRG": [10.0],
                "CLS_SALE_MT_AVRG": [5.0],
                "SU_OPR_SALE_MT_AVRG": [11.0],
                "SU_CLS_SALE_MT_AVRG": [6.0],
            }
        )
        result = build_commercial_change_features(frame)
        self.assertEqual(result["commercial_change_lh"].iloc[0], 1)
        self.assertEqual(result[["commercial_change_ll", "commercial_change_hl", "commercial_change_hh"]].sum(axis=1).iloc[0], 0)

    def test_winsorization_records_bounds(self) -> None:
        frame = pd.DataFrame({"feature": list(range(100)) + [10_000]})
        result, bounds = winsorize_features(frame, ["feature"], lower_quantile=0.01, upper_quantile=0.99)
        self.assertIn("feature", bounds)
        self.assertLess(result["feature"].max(), 10_000)


if __name__ == "__main__":
    unittest.main()
