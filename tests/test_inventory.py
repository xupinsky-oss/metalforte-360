import unittest

import pandas as pd

from src.inventory import build_inventory_analysis, prepare_stock


class InventoryAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.stock = pd.DataFrame([
            {"Grupo": "TUBOS", "Código": "1", "Descrição Produto": "Produto A", "Saldo Total": 1000, "Reserva Total": 100},
            {"Grupo": "TUBOS", "Código": "2", "Descrição Produto": "Produto B", "Saldo Total": 20, "Reserva Total": 0},
            {"Grupo": "TELHAS", "Código": "3", "Descrição Produto": "Produto C", "Saldo Total": 500, "Reserva Total": 0},
            {"Grupo": "TELHAS", "Código": "4", "Descrição Produto": "Produto D", "Saldo Total": 0, "Reserva Total": 0},
        ])
        end = pd.Timestamp("2026-09-30")
        self.sales = pd.DataFrame([
            {"Data": end - pd.Timedelta(days=5), "Produto Codigo": "1", "Produto": "Produto A", "Grupo Produto": "Tubos", "Subgrupo Produto": "S1", "Tipo Produto": "T1", "Faturamento": 10000, "Peso": 900, "Pedido": "P1"},
            {"Data": end - pd.Timedelta(days=10), "Produto Codigo": "2", "Produto": "Produto B", "Grupo Produto": "Tubos", "Subgrupo Produto": "S1", "Tipo Produto": "T1", "Faturamento": 1000, "Peso": 100, "Pedido": "P2"},
            {"Data": end - pd.Timedelta(days=15), "Produto Codigo": "4", "Produto": "Produto D", "Grupo Produto": "Telhas", "Subgrupo Produto": "S2", "Tipo Produto": "T2", "Faturamento": 100, "Peso": 10, "Pedido": "P3"},
        ])

    def test_available_stock_is_balance_less_reservation(self):
        result = prepare_stock(self.stock)
        row = result[result["Produto Codigo"] == "1"].iloc[0]
        self.assertEqual(row["Estoque disponível (kg)"], 900)

    def test_pt_br_stock_numbers_are_parsed(self):
        stock = pd.DataFrame([{"Grupo": "TUBOS", "Código": "9", "Descrição Produto": "Produto", "Saldo Total": "1.234,50", "Reserva Total": "34,50"}])
        result = prepare_stock(stock)
        self.assertEqual(result.iloc[0]["Estoque disponível (kg)"], 1200)

    def test_abc_and_stock_coverage_are_independent(self):
        result = build_inventory_analysis(self.stock, self.sales, months=3, abc_measure="Peso").set_index("Produto Codigo")
        self.assertEqual(result.loc["1", "Curva ABC"], "A")
        self.assertEqual(result.loc["1", "Giro"], "Alto giro")
        self.assertEqual(result.loc["3", "Giro"], "Sem giro")
        self.assertEqual(result.loc["3", "Cobertura"], "Sem giro")
        self.assertEqual(result.loc["4", "Cobertura"], "Ruptura")

    def test_window_metadata_is_exposed(self):
        result = build_inventory_analysis(self.stock, self.sales, months=3)
        self.assertEqual(result.attrs["end_date"], pd.Timestamp("2026-09-25"))
        self.assertGreater(result.attrs["calendar_days"], 80)


if __name__ == "__main__":
    unittest.main()
