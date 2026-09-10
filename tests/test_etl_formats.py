import unittest
from unittest.mock import patch

import pandas as pd

from atualizar_gooddata import collect_target_periods, parse_raw


class EtlFormatTests(unittest.TestCase):
    def test_indicator_accepts_single_column_csv(self):
        result = parse_raw(b'"(43) Vlr Orcamento"\n"24749217,15"\n', allow_single_column=True)
        self.assertEqual(result.shape, (1, 1))

    def test_transaction_report_rejects_single_column_csv(self):
        with self.assertRaisesRegex(ValueError, "Formato RAW"):
            parse_raw(b'erro\nconteudo\n')

    def test_semicolon_report_is_detected(self):
        result = parse_raw(b'coluna_a;coluna_b\n1;2\n')
        self.assertEqual(result.shape, (1, 2))

    def test_collects_previous_current_and_future_targets(self):
        detail = pd.DataFrame({"Vendedor": ["ANA"], "Grupo Prod.": ["AÇO"], "Meta Mês": [2]})
        value = pd.DataFrame({"Vlr Orçamento": [10000]})

        class Connector:
            def raw_report(self, report_id, offset_from=0, offset_to=0):
                if report_id == "11081881":
                    return b'Vendedor;Grupo Prod.;Meta Mes\nANA;ACO;2\n'
                return b'Vlr Orcamento\n10000\n'

        with patch.dict("os.environ", {"TOTVS_TARGET_OFFSET_FROM": "-1", "TOTVS_TARGET_OFFSET_TO": "1"}):
            result = collect_target_periods(Connector(), detail, value)
        self.assertEqual(result["Competência"].nunique(), 3)
        self.assertAlmostEqual(result["Meta R$"].sum(), 30000)
        self.assertAlmostEqual(result["Meta KG"].sum(), 6000)


if __name__ == "__main__":
    unittest.main()
