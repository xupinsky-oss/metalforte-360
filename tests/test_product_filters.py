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
            "Tipologia Cliente": ["REVENDA", "CONSTRUTORA"],
            "Subgrupo Produto": ["LEVE", "PESADO"],
            "ESPEC.": ["06 ZC", "08 ZC"],
            "Sub Espec.": ["04 PP", "05 PP"],
        })

        result = apply_filters(
            frame, subgrupo=["LEVE"], espec=["06 ZC"], sub_espec=["04 PP"]
        )

        self.assertEqual(result["Produto"].tolist(), ["A"])

    def test_customer_type_filter_uses_tipologia_cliente(self):
        frame = pd.DataFrame({
            "Data": pd.to_datetime(["2026-09-01", "2026-09-02", "2026-09-03"]),
            "Ano": [2026, 2026, 2026],
            "Cliente": ["CLIENTE 1", "CLIENTE 2", "CLIENTE 3"],
            "Produto": ["A", "B", "C"],
            "Tipologia Cliente": ["REVENDA", "CONSTRUTORA", "REVENDA"],
        })

        result = apply_filters(frame, tipologia=["REVENDA"])

        self.assertEqual(result["Cliente"].tolist(), ["CLIENTE 1", "CLIENTE 3"])


if __name__ == "__main__":
    unittest.main()
