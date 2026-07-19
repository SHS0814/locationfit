"""Tests for dataset-specific local quarter selection."""

import unittest

import pandas as pd

from scripts.download_seoul_data import select_quarter_rows


class LocalQuarterFilterTests(unittest.TestCase):
    def test_selects_api_quarter_column(self) -> None:
        frame = pd.DataFrame(
            [
                {"STDR_YYQU_CD": "20211", "TRDAR_CD": "1"},
                {"STDR_YYQU_CD": "20212", "TRDAR_CD": "2"},
            ]
        )
        rows = select_quarter_rows(frame, 20211)
        self.assertEqual(rows, [{"STDR_YYQU_CD": "20211", "TRDAR_CD": "1"}])


if __name__ == "__main__":
    unittest.main()
