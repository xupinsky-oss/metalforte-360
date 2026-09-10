import unittest

from atualizar_gooddata import parse_raw


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


if __name__ == "__main__":
    unittest.main()
