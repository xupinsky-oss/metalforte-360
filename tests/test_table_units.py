import ast
import unittest
from pathlib import Path


def _load_column_classifiers():
    source = Path("app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {"_is_fraction_percent", "_is_weight_column", "_is_money_column"}
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "app.py", "exec"), namespace)
    return namespace


class TableUnitFormattingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classifiers = _load_column_classifiers()

    def test_target_weight_columns_are_not_money(self):
        is_weight = self.classifiers["_is_weight_column"]
        is_money = self.classifiers["_is_money_column"]
        for column in ("Meta KG", "Realizado KG", "Saldo KG", "KG faturado"):
            self.assertTrue(is_weight(column), column)
            self.assertFalse(is_money(column), column)

    def test_price_per_kg_remains_money(self):
        is_weight = self.classifiers["_is_weight_column"]
        is_money = self.classifiers["_is_money_column"]
        self.assertFalse(is_weight("Preço médio/kg"))
        self.assertTrue(is_money("Preço médio/kg"))


if __name__ == "__main__":
    unittest.main()
