import unittest

from streamlit.testing.v1 import AppTest


class StreamlitTargetSmokeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
