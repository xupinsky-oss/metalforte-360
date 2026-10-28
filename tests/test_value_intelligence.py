import unittest

import pandas as pd

from src.value_intelligence import (
    iqr_inlier_mask,
    customer_rfmv,
    margin_volume_quadrants,
    portfolio_health,
    price_reference_matrix,
    rfmv_class,
    weighted_quantile,
)


def _sale(client, seller, date, revenue, weight, margin, invoice, product="TUBO", segment="REVENDA"):
    return {
        "Data": pd.Timestamp(date), "Cod Cliente": client, "Cliente": f"Cliente {client}",
        "Vendedor": seller, "Segmento Cliente": segment, "UF": "GO", "Município": "GOIÂNIA",
        "Faturamento": revenue, "Peso": weight, "Margem": margin, "NF": invoice,
        "Produto": product, "Grupo Produto": product, "Subgrupo Produto": product,
        "Tipo Produto": product, "ESPEC.": product,
    }


class ValueIntelligenceTests(unittest.TestCase):
    def test_iqr_inlier_mask_hides_extreme_value_only(self):
        values = pd.Series([10, 11, 12, 13, 14, 15, 16, 1000])
        mask = iqr_inlier_mask(values)
        self.assertEqual(int(mask.sum()), 7)
        self.assertFalse(bool(mask.iloc[-1]))

    def test_weighted_quantile(self):
        self.assertEqual(weighted_quantile([1, 2, 10], [1, 1, 1], 0.5), 2)
        self.assertGreater(weighted_quantile([1, 2, 10], [1, 1, 10], 0.5), 2)

    def test_portfolio_health_status_and_coverage(self):
        end = pd.Timestamp("2026-09-30")
        rows = [
            _sale("A", "VENDEDOR 1", "2025-01-01", 100, 10, 20, "A0"),
            _sale("A", "VENDEDOR 1", "2026-09-20", 200, 20, 40, "A1"),
            _sale("B", "VENDEDOR 1", "2026-06-02", 100, 10, 15, "B1"),
            _sale("C", "VENDEDOR 1", "2026-01-23", 100, 10, 10, "C1"),
            _sale("D", "VENDEDOR 1", "2026-09-25", 100, 10, 12, "D1"),
        ]
        summary, detail = portfolio_health(pd.DataFrame(rows), end, inactivity_days=180)
        self.assertEqual(int(summary.iloc[0]["Carteira total"]), 4)
        self.assertAlmostEqual(float(summary.iloc[0]["Cobertura 90d"]), 0.5)
        self.assertEqual(detail.set_index("Cod Cliente").loc["B", "Status"], "Em risco")
        self.assertEqual(detail.set_index("Cod Cliente").loc["C", "Status"], "Inativo")
        self.assertEqual(detail.set_index("Cod Cliente").loc["D", "Status"], "Novo")

    def test_customer_rfmv_uses_relationship_years_since_2024(self):
        rows = []
        for year in (2024, 2025, 2026):
            for order in range(6):
                rows.append(_sale(
                    "A", "V1", f"{year}-{order + 1:02d}-05", 1_000, 100, 150,
                    f"A-{year}-{order}",
                ))
        for order in range(6):
            rows.append(_sale("B", "V1", f"2024-{order + 1:02d}-10", 200, 20, 20, f"B-2024-{order}"))
        rows.append(_sale("B", "V1", "2026-09-10", 200, 20, 20, "B-2026"))
        rows.append(_sale("C", "V2", "2026-09-12", 10, 1, 1, "C-2026"))

        result = customer_rfmv(pd.DataFrame(rows), "2026-09-30").set_index("Cod Cliente")

        self.assertEqual(int(result.loc["A", "Nota R"]), 5)
        self.assertEqual(int(result.loc["B", "Nota R"]), 2)
        self.assertEqual(int(result.loc["C", "Nota R"]), 1)
        self.assertEqual(result.loc["A", "Classe RFMV"], "A")
        self.assertEqual(result.loc["A", "Código RFMV"], "R5-F5-M5-V5")
        self.assertTrue(result["Nota RFMV"].between(4, 20).all())

    def test_rfmv_class_uses_requested_total_score_bands(self):
        classes = rfmv_class([0, 5, 6, 10, 11, 15, 16, 20]).tolist()
        self.assertEqual(classes, ["D", "D", "C", "C", "B", "B", "A", "A"])

    def test_price_matrix_excludes_unreliable_weight_products(self):
        rows = []
        for index, price in enumerate((6, 7, 8, 9, 10), start=1):
            rows.append(_sale(str(index), "V1", f"2026-0{index}-15", price * 100, 100, price * 20, f"N{index}"))
        rows.append(_sale("X", "V1", "2026-09-01", 5000, 10, 500, "TX", product="TELHA ISOTÉRMICA"))
        matrix = price_reference_matrix(pd.DataFrame(rows), "2026-09-30", "Grupo Produto", months=12)
        self.assertEqual(matrix["Grupo Produto"].tolist(), ["TUBO"])
        self.assertAlmostEqual(float(matrix.iloc[0]["Preço referência/kg"]), 8)
        self.assertEqual(matrix.iloc[0]["Amostra confiável"], "Sim")

    def test_margin_volume_quadrants(self):
        rows = [
            _sale("A", "V1", "2026-09-01", 10_000, 1_000, 2_000, "A", segment="A"),
            _sale("B", "V1", "2026-09-01", 20_000, 2_000, 2_000, "B", segment="B"),
            _sale("C", "V1", "2026-09-01", 30_000, 3_000, 6_000, "C", segment="C"),
            _sale("D", "V1", "2026-09-01", 40_000, 4_000, 4_000, "D", segment="D"),
        ]
        view, cut = margin_volume_quadrants(pd.DataFrame(rows), "Segmento Cliente", margin_floor=0.14)
        result = view.set_index("Segmento Cliente")["Quadrante"].to_dict()
        self.assertEqual(cut, 2.5)
        self.assertEqual(result, {"A": "Desenvolver", "B": "Rever", "C": "Proteger", "D": "Reprecificar"})


if __name__ == "__main__":
    unittest.main()
