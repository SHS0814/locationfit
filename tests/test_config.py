"""Tests for quarter generation and validation."""

import unittest

from src.data.config import generate_quarters, validate_quarter


class QuarterTests(unittest.TestCase):
    def test_generates_twenty_quarters(self) -> None:
        quarters = generate_quarters(20211, 20254)
        self.assertEqual(len(quarters), 20)
        self.assertEqual((quarters[0], quarters[-1]), (20211, 20254))

    def test_rejects_invalid_number(self) -> None:
        with self.assertRaises(ValueError):
            validate_quarter(20215)

    def test_rejects_reversed_period(self) -> None:
        with self.assertRaises(ValueError):
            generate_quarters(20221, 20214)


if __name__ == "__main__":
    unittest.main()
