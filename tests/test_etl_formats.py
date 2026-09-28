import unittest
from unittest.mock import patch

import pandas as pd

from atualizar_gooddata import build_flow_timeline, collect_target_periods, extract_indicator_percentage, extract_loss_reasons, parse_raw


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

    def test_percentage_indicator_keeps_decimal_scale(self):
        self.assertAlmostEqual(extract_indicator_percentage(pd.DataFrame({"Conversão": ["68%"]})), .68)

    def test_loss_detail_keeps_reason_value_and_weight(self):
        records = extract_loss_reasons(pd.DataFrame({
            "Motivo da perda": ["Preço concorrente", "Falta de estoque", "Sum"],
            "Valor da perda": ["R$ 1.800,00", "R$ 700,00", "R$ 2.500,00"],
            "Peso da perda": ["250,00 Kg", "90,00 Kg", "340,00 Kg"],
        }))
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["Motivo da perda"], "Preço concorrente")
        self.assertEqual(records[0]["Valor perdido (R$)"], 1800)
        self.assertEqual(records[1]["Peso perdido (kg)"], 90)

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

    def test_quote_detail_preserves_margin_and_commercial_dimensions(self):
        flow = build_flow_timeline({
            "orcamentos_abertos_detalhe": pd.DataFrame({
                "Nome Vendedor": ["ANA"], "Nome Cliente": ["CLIENTE A"],
                "Emissão": ["28/09/2026"], "Pedido": ["CAD001"], "Peso": ["1.250,50"],
                "Total": ["R$ 12.500,00"], "Projeção Custo": ["R$ 8.000,00"],
                "Projeção Imposto": ["R$ 1.000,00"], "Projeção Margem": ["R$ 3.500,00"], "%": ["28,00%"],
            })
        })
        row = flow.iloc[0]
        self.assertEqual(row["Origem"], "Orçamento em aberto")
        self.assertEqual(row["Vendedor"], "ANA")
        self.assertEqual(row["Cliente"], "CLIENTE A")
        self.assertAlmostEqual(row["Peso"], 1250.5)
        self.assertAlmostEqual(row["Projeção Margem"], 3500)
        self.assertAlmostEqual(row["Margem %"], .28)


if __name__ == "__main__":
    unittest.main()
