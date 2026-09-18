import unittest

import pandas as pd

from src.assistant import SUGGESTED_QUESTIONS, answer


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.history = pd.DataFrame({
            "Data": pd.to_datetime(["2026-06-01", "2026-08-10", "2026-08-18", "2026-09-05", "2026-09-10"]),
            "Faturamento": [5000.0, 10000.0, 8000.0, 12000.0, 6000.0],
            "Margem": [800.0, 1500.0, -200.0, 2100.0, 900.0],
            "Peso": [500.0, 1000.0, 900.0, 1200.0, 600.0],
            "NF": ["1", "2", "3", "4", "5"],
            "Cliente": ["INATIVO", "ALFA", "BETA", "ALFA", "GAMA"],
            "Produto": ["TELHA", "TELHA", "TUBO", "TELHA", "PERFIL"],
            "Vendedor": ["ANA", "ANA", "BRUNO", "ANA", "BRUNO"],
            "Grupo Produto": ["TELHA", "TELHA", "TUBO", "TELHA", "PERFIL"],
            "Cod Cliente": ["C1", "C2", "C3", "C2", "C4"],
            "Mes": [6, 8, 8, 9, 9],
            "UF": ["MG", "MG", "SP", "MG", "SP"],
            "Município": ["Betim", "Betim", "São Paulo", "Betim", "Campinas"],
            "Benchmark Grupo": [9.5, 9.5, 10.0, 9.5, 10.0],
            "Preço Real Kg": [10.0, 10.0, 8.89, 10.0, 10.0],
        })
        self.current = self.history[self.history["Data"].dt.month == 9].copy()

    def test_ready_questions_return_safe_answer(self):
        for _, question in SUGGESTED_QUESTIONS:
            with self.subTest(question=question):
                response = answer(question, self.current, self.history, "2026-09-01", "2026-09-30")
                self.assertTrue(response.strip())
                self.assertNotIn("nan%", response.lower())
                self.assertNotIn("।", response)

    def test_empty_filtered_population_is_explicit(self):
        response = answer("Como estamos no período?", self.current.iloc[0:0], self.history)
        self.assertIn("Não há registros", response)

    def test_inactivity_uses_history_until_filter_end(self):
        response = answer("Quais clientes estão sem comprar há 90 dias?", self.current, self.history, "2026-09-01", "2026-09-30")
        self.assertIn("INATIVO", response)


if __name__ == "__main__":
    unittest.main()
