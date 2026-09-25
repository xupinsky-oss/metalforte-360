import unittest

import pandas as pd

from atualizar_gooddata import consolidate, load_product_matrix, prepare_product_matrix


def _downloaded_frames():
    return {
        "faturamento": pd.DataFrame([[
            "01", "01/09/2026", "ANA", "CLIENTE", "100", "1", "PROD DESC",
            "5102", "001", 1000.0, 100.0, 10.0,
        ]]),
        "clientes_pedidos": pd.DataFrame([[
            "ANA", "10", "CLIENTE", "31/08/2026", "500", "100", "1",
            "PROD DESC", 100.0, 1000.0, 10.0, 0.20,
        ]]),
        "margem": pd.DataFrame([[
            "500", "100", "1", "3801", "PROD DESC", 0.20, 200.0, 10.0,
            100.0, 0.0, 1000.0, 100.0, 0.0, 100.0, 8.0, 800.0,
            0.0, 0.0, 0.0, 0.0,
        ]]),
        "produto_classificacao": pd.DataFrame([[
            "3801", "PROD CAD", 0.80, "GRUPO LEGADO", "TIPO LEGADO", 0.0, 0.0,
        ]]),
        "cliente_geo": pd.DataFrame([[
            "10", "CLIENTE", "SP", "Campinas", 1000.0,
        ]]),
        "cliente_classificacao": pd.DataFrame([[
            "10", "01", "CLIENTE", "000", "INDÚSTRIA", "FABRICANTE", "ANA",
        ]]),
        "preco_benchmark": pd.DataFrame([[
            "Sep 2026", "GRUPO LEGADO", 9.5,
        ]]),
    }


def _matrix():
    return pd.DataFrame({
        "Produto Codigo": ["00003801"],
        "Tipo Produto Matriz": ["PA"],
        "Grupo Produto Matriz": ["0002 Bobininha"],
        "Subgrupo Produto": ["Linha leve"],
        "ESPEC.": ["06 ZC"],
        "Sub Espec.": ["04 PP"],
        "Espessura Matriz": [0.50],
    })


class ProductMatrixTests(unittest.TestCase):
    def test_versioned_matrix_is_unique_and_has_expected_size(self):
        matrix = load_product_matrix()
        self.assertEqual(len(matrix), 2158)
        self.assertEqual(matrix["Produto Codigo"].nunique(), 2158)
        self.assertEqual(int(matrix["ESPEC."].notna().sum()), 1983)

    def test_consolidation_uses_matrix_and_keeps_benchmark_join(self):
        result = consolidate(_downloaded_frames(), product_matrix=_matrix())
        row = result.iloc[0]
        self.assertEqual(row["Grupo Produto"], "0002 Bobininha")
        self.assertEqual(row["Tipo Produto"], "PA")
        self.assertEqual(row["Subgrupo Produto"], "Linha leve")
        self.assertEqual(row["ESPEC."], "06 ZC")
        self.assertEqual(row["Sub Espec."], "04 PP")
        self.assertEqual(row["Fonte Classificação Produto"], "Matriz Ecommerce")
        self.assertAlmostEqual(row["Espessura"], 0.50)
        self.assertAlmostEqual(row["Benchmark Grupo"], 9.5)

    def test_duplicate_product_code_is_rejected(self):
        duplicate = pd.concat([_matrix(), _matrix()], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "códigos duplicados"):
            prepare_product_matrix(duplicate)


if __name__ == "__main__":
    unittest.main()
