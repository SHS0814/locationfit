"""Tests for historical area × industry evidence engineering."""

import unittest

import numpy as np
import pandas as pd

from src.data.config import generate_quarters
from src.features.area_industry_evidence import (
    prepare_evidence_panel,
    ratio_or_nan,
    summarize_evidence,
)


class AreaIndustryEvidenceTests(unittest.TestCase):
    def test_ratio_or_nan_preserves_unknown_denominators(self) -> None:
        result = ratio_or_nan(pd.Series([4.0, 2.0, 1.0]), pd.Series([2.0, 0.0, np.nan]))
        self.assertEqual(result.iloc[0], 2.0)
        self.assertTrue(result.iloc[1:].isna().all())

    def test_stale_combination_has_lower_reliability(self) -> None:
        quarters = [str(value) for value in generate_quarters(20211, 20254)]
        sales_rows = []
        store_rows = []
        commercial_rows = []
        for index, quarter in enumerate(quarters):
            for area_code, industry_code in (("1", "i1"), ("2", "i2")):
                store_rows.append(
                    {
                        "quarter": quarter,
                        "area_code": area_code,
                        "industry_code": industry_code,
                        "SIMILR_INDUTY_STOR_CO": 10.0,
                        "FRC_STOR_CO": 2.0,
                        "OPBIZ_RT": 5.0,
                        "CLSBIZ_RT": 3.0,
                    }
                )
            commercial_rows.extend(
                [
                    {
                        "quarter": quarter,
                        "area_code": area_code,
                        "TRDAR_CHNGE_IX": "LL",
                        "TRDAR_CHNGE_IX_NM": "다이나믹",
                        "OPR_SALE_MT_AVRG": 60.0,
                        "CLS_SALE_MT_AVRG": 40.0,
                    }
                    for area_code in ("1", "2")
                ]
            )
            sales_rows.append(
                {
                    "quarter": quarter,
                    "area_code": "1",
                    "area_name": "a1",
                    "industry_code": "i1",
                    "industry_name": "업종1",
                    "당월_매출_금액": 100.0 + index,
                }
            )
            if index < 10:
                sales_rows.append(
                    {
                        "quarter": quarter,
                        "area_code": "2",
                        "area_name": "a2",
                        "industry_code": "i2",
                        "industry_name": "업종2",
                        "당월_매출_금액": 50.0 + index,
                    }
                )
        panel, identities = prepare_evidence_panel(
            pd.DataFrame(sales_rows),
            pd.DataFrame(store_rows),
            pd.DataFrame(commercial_rows),
            quarters,
        )
        profile = pd.DataFrame(
            [
                {
                    "quarter": quarter,
                    "area_code": area_code,
                    "area_size_sqm": 100_000.0,
                    "data_reliability": 1.0,
                    "observation_count": 8,
                }
                for quarter in quarters[-8:]
                for area_code in ("1", "2")
            ]
        )
        evidence, _ = summarize_evidence(panel, identities, profile, quarters)
        self.assertEqual(len(evidence), 2)
        self.assertEqual(evidence.duplicated(["area_code", "industry_code"]).sum(), 0)
        current = evidence.loc[evidence["industry_code"].eq("i1")].iloc[0]
        stale = evidence.loc[evidence["industry_code"].eq("i2")].iloc[0]
        self.assertEqual(current["stale_observation_flag"], 0)
        self.assertEqual(stale["stale_observation_flag"], 1)
        self.assertEqual(stale["current_sales_missing_flag"], 1)
        self.assertLess(stale["data_reliability"], current["data_reliability"])


if __name__ == "__main__":
    unittest.main()
