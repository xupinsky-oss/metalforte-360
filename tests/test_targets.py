import unittest

import pandas as pd

from src.product_groups import normalize_product_group
from src.targets import allocate_target, consolidate_targets, merge_target_history, target_scope


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.meta_kg = pd.DataFrame({
            "Vendedor": ["ANA", "BRUNO"],
            "Grupo Prod.": ["AÇO", "TUBOS"],
            "Meta Mês": [1.5, 2.5],
        })
        self.meta_value = pd.DataFrame({"(43) Vlr Orçamento": [40000.0]})

    def test_official_totals_reconcile(self):
        result = consolidate_targets(self.meta_kg, self.meta_value, "2026-09-01")
        self.assertAlmostEqual(result["Meta KG"].sum(), 4000.0)
        self.assertAlmostEqual(result["Meta R$"].sum(), 40000.0)
        self.assertEqual(result["Competência"].nunique(), 1)

    def test_product_group_names_use_matrix_nomenclature(self):
        self.assertEqual(normalize_product_group("14 - TUBO"), "0014 Tubos")
        self.assertEqual(normalize_product_group("Grupo Produto: tubos"), "0014 Tubos")
        self.assertEqual(normalize_product_group("0007 ISOTÉRMICOS"), "0007 Isotermicos")
        self.assertEqual(normalize_product_group("promoção"), "0025 PROMOCAO")

        duplicated = pd.DataFrame({
            "Vendedor": ["ANA", "ANA", "ANA"],
            "Grupo Prod.": ["TUBO", "0014 - TUBOS", "Grupo Produto: Tubos"],
            "Meta Mês": [1.0, 2.0, 3.0],
        })
        result = consolidate_targets(duplicated, self.meta_value, "2026-09-01")
        self.assertEqual(result["Grupo Produto"].tolist(), ["0014 Tubos"])
        self.assertAlmostEqual(result["Meta KG"].sum(), 6000.0)

    def test_history_replaces_only_current_month(self):
        august = consolidate_targets(self.meta_kg, self.meta_value, "2026-08-01")
        september = consolidate_targets(self.meta_kg, self.meta_value, "2026-09-01")
        merged = merge_target_history(august, september)
        self.assertEqual(len(merged), 4)
        self.assertEqual(merged["Competência"].nunique(), 2)

    def test_client_allocation_preserves_target(self):
        targets = consolidate_targets(self.meta_kg.iloc[:1], self.meta_value, "2026-09-01")
        history = pd.DataFrame({
            "Data": pd.to_datetime(["2026-05-31", "2026-06-10", "2026-08-10"]),
            "Vendedor": ["ANA", "ANA", "ANA"], "Grupo Produto": ["AÇO", "AÇO", "AÇO"],
            "Cliente": ["FORA DA JANELA", "CLIENTE 1", "CLIENTE 2"],
            "Produto": ["P0", "P1", "P2"],
            "Faturamento": [10000.0, 300.0, 100.0], "Peso": [10000.0, 60.0, 40.0],
        })
        result, reserve = allocate_target(targets, history, "Cliente")
        self.assertAlmostEqual(result["Meta R$"].sum(), targets["Meta R$"].sum())
        self.assertAlmostEqual(result["Meta KG"].sum(), targets["Meta KG"].sum())
        self.assertEqual(reserve, {"Meta R$": 0.0, "Meta KG": 0.0})
        allocated = result.set_index("Cliente")
        self.assertNotIn("FORA DA JANELA", allocated.index)
        self.assertAlmostEqual(allocated.loc["CLIENTE 1", "Meta R$"], 24000.0)
        self.assertAlmostEqual(allocated.loc["CLIENTE 2", "Meta R$"], 16000.0)

        products, product_reserve = allocate_target(targets, history, "Produto")
        product_allocated = products.set_index("Produto")
        self.assertAlmostEqual(product_allocated.loc["P1", "Meta KG"] / targets["Meta KG"].sum(), 0.60)
        self.assertAlmostEqual(product_allocated.loc["P2", "Meta KG"] / targets["Meta KG"].sum(), 0.40)
        self.assertEqual(product_reserve, {"Meta R$": 0.0, "Meta KG": 0.0})

    def test_allocation_matches_legacy_target_to_matrix_group(self):
        targets = consolidate_targets(
            pd.DataFrame({"Vendedor": ["ANA"], "Grupo Prod.": ["TUBO"], "Meta Mês": [1.0]}),
            self.meta_value, "2026-09-01",
        )
        history = pd.DataFrame({
            "Data": pd.to_datetime(["2026-08-10"]),
            "Vendedor": ["ANA"], "Grupo Produto": ["0014 Tubos"],
            "Cliente": ["CLIENTE 1"], "Produto": ["P1"],
            "Faturamento": [1000.0], "Peso": [100.0],
        })
        result, reserve = allocate_target(targets, history, "Cliente")
        self.assertEqual(result["Cliente"].tolist(), ["CLIENTE 1"])
        self.assertEqual(reserve, {"Meta R$": 0.0, "Meta KG": 0.0})

    def test_scope_uses_explicit_filters(self):
        targets = consolidate_targets(self.meta_kg, self.meta_value, "2026-09-01")
        result = target_scope(targets, "2026-09-01", "2026-09-30", sellers=["ANA"])
        self.assertEqual(result["Vendedor"].unique().tolist(), ["ANA"])

    def test_scope_supports_future_competence(self):
        future = consolidate_targets(self.meta_kg, self.meta_value, "2027-03-01")
        result = target_scope(future, "2027-03-01", "2027-03-31")
        self.assertEqual(result["Competência"].dt.strftime("%Y-%m").unique().tolist(), ["2027-03"])

    def test_invalid_official_value_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "meta mensal em R\\$ positiva"):
            consolidate_targets(self.meta_kg, pd.DataFrame({"Vlr Orçamento": [0]}), "2026-09-01")


if __name__ == "__main__":
    unittest.main()
