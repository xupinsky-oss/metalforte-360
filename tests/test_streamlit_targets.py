import unittest
import inspect

from streamlit.testing.v1 import AppTest

from src.operational_dashboard import _metric_card_html, render


class StreamlitTargetSmokeTests(unittest.TestCase):
    def test_render_accepts_commercial_indicators_contract(self):
        self.assertIn("commercial_indicators", inspect.signature(render).parameters)

    def test_metric_card_fragment_is_not_parsed_as_markdown_code(self):
        fragment = _metric_card_html("Faturamento", "R$ 1.000,00")
        self.assertNotRegex(fragment, r"(?m)^ {4}")

    def test_target_page_renders_cards_chart_and_table(self):
        script = r'''
import pandas as pd
import streamlit as st
from src.operational_dashboard import _targets_view
from src.targets import consolidate_targets

sales = pd.DataFrame({
    "Data": pd.to_datetime(["2026-01-10", "2026-09-05"]),
    "Vendedor": ["ANA", "ANA"], "Grupo Produto": ["AÇO", "AÇO"],
    "Cliente": ["CLIENTE 1", "CLIENTE 1"], "Produto": ["P1", "P1"],
    "Faturamento": [10000.0, 4000.0], "Peso": [1000.0, 400.0], "Margem": [1500.0, 600.0],
})
targets = consolidate_targets(
    pd.DataFrame({"Vendedor": ["ANA"], "Grupo Prod.": ["AÇO"], "Meta Mês": [1.0]}),
    pd.DataFrame({"Vlr Orçamento": [10000.0]}), "2026-09-01",
)
brl=lambda value: f"R$ {value:,.2f}"
pct=lambda value: f"{value*100:.2f}%"
_targets_view(
    sales[sales["Data"].dt.month == 9], sales, targets, "2026-09-01", "2026-09-30",
    brl, pct, lambda fig: st.plotly_chart(fig), lambda frame, **kwargs: st.dataframe(frame),
    {}, False,
)
'''
        app = AppTest.from_string(script).run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        self.assertGreaterEqual(len(app.metric), 4)

    def test_responsive_cards_render_without_legacy_component(self):
        script = r'''
import pandas as pd
import streamlit as st
from src.operational_dashboard import _comparison_cards, _daily

brl=lambda value: f"R$ {value:,.2f}"
brl2=brl
pct=lambda value: f"{value*100:.2f}%"
current={"revenue": 1000.0, "weight": 100.0, "margin_pct": .2, "price_kg": 10.0, "positive_clients": 2}
reference={"revenue": 900.0, "weight": 90.0, "margin_pct": .18, "price_kg": 10.0, "positive_clients": 1}
_comparison_cards(current, reference, "mês anterior", brl, brl2, pct)
sales = pd.DataFrame({
    "Data": pd.to_datetime(["2026-09-08", "2026-09-09"]),
    "Cliente": ["A", "B"], "Faturamento": [900.0, 1000.0],
    "Peso": [90.0, 100.0], "Margem": [180.0, 200.0],
    "NF": [1, 2], "Produto": ["P1", "P2"],
})
_daily(sales, sales, "2026-09-09", brl, brl2, pct,
       lambda fig: st.plotly_chart(fig), lambda frame, **kwargs: st.dataframe(frame))
'''
        app = AppTest.from_string(script).run(timeout=20)
        self.assertEqual(len(app.exception), 0)


if __name__ == "__main__":
    unittest.main()
