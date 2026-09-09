import unittest

import pandas as pd

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

    def test_history_replaces_only_current_month(self):
        august = consolidate_targets(self.meta_kg, self.meta_value, "2026-08-01")
        september = consolidate_targets(self.meta_kg, self.meta_value, "2026-09-01")
        merged = merge_target_history(august, september)
        self.assertEqual(len(merged), 4)
        self.assertEqual(merged["Competência"].nunique(), 2)

    def test_client_allocation_preserves_target(self):
        targets = consolidate_targets(self.meta_kg.iloc[:1], self.meta_value, "2026-09-01")
        history = pd.DataFrame({
            "Data": pd.to_datetime(["2026-01-10", "2026-02-10"]),
            "Vendedor": ["ANA", "ANA"], "Grupo Produto": ["AÇO", "AÇO"],
            "Cliente": ["CLIENTE 1", "CLIENTE 2"], "Produto": ["P1", "P2"],
            "Faturamento": [300.0, 100.0], "Peso": [60.0, 40.0],
        })
        result, reserve = allocate_target(targets, history, "Cliente")
        self.assertAlmostEqual(result["Meta R$"].sum(), targets["Meta R$"].sum())
        self.assertAlmostEqual(result["Meta KG"].sum(), targets["Meta KG"].sum())
        self.assertEqual(reserve, {"Meta R$": 0.0, "Meta KG": 0.0})

    def test_scope_uses_explicit_filters(self):
        targets = consolidate_targets(self.meta_kg, self.meta_value, "2026-09-01")
        result = target_scope(targets, "2026-09-01", "2026-09-30", sellers=["ANA"])
        self.assertEqual(result["Vendedor"].unique().tolist(), ["ANA"])

    def test_invalid_official_value_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "meta mensal em R\\$ positiva"):
            consolidate_targets(self.meta_kg, pd.DataFrame({"Vlr Orçamento": [0]}), "2026-09-01")


if __name__ == "__main__":
    unittest.main()
