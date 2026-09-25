import unittest

import pandas as pd

from src.data import apply_filters


class ProductFilterTests(unittest.TestCase):
    def test_product_classification_filters_are_applied_together(self):
        frame = pd.DataFrame({
            "Data": pd.to_datetime(["2026-09-01", "2026-09-02"]),
            "Ano": [2026, 2026],
            "Produto": ["A", "B"],
            "Cliente": ["CLIENTE 1", "CLIENTE 2"],
            "Subgrupo Produto": ["LEVE", "PESADO"],
            "ESPEC.": ["06 ZC", "08 ZC"],
            "Sub Espec.": ["04 PP", "05 PP"],
        })

        result = apply_filters(
            frame, subgrupo=["LEVE"], espec=["06 ZC"], sub_espec=["04 PP"]
        )

        self.assertEqual(result["Produto"].tolist(), ["A"])


if __name__ == "__main__":
    unittest.main()
