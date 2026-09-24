import unittest
import inspect
from pathlib import Path
from tempfile import TemporaryDirectory
import pandas as pd

from streamlit.testing.v1 import AppTest

from src.operational_dashboard import (
    _flow_deadlines, _flow_event_summary, _funnel_frame, _metric_card_html,
    _flow_current_positions, _monthly_activity_matrix, _municipal_map_data,
    _monthly_projection, _selected_plotly_date, render,
)
from src.commercial_intelligence import customer_portfolio, purchase_seasonality
from src.data import load_data


class StreamlitTargetSmokeTests(unittest.TestCase):
    def test_load_data_defines_channel_from_customer_segment(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "base.csv"
            pd.DataFrame({
                "Data": ["2026-09-01", "2026-09-02"],
                "Segmento Cliente": ["INDÚSTRIA", "REVENDA"],
                "Canal": ["LEGADO A", "LEGADO B"],
                "Faturamento": [100.0, 200.0],
            }).to_csv(path, index=False)
            loaded = load_data(path)
        self.assertEqual(loaded["Canal"].tolist(), ["INDÚSTRIA", "REVENDA"])

    def test_monthly_projection_uses_calendar_days_and_remaining_days(self):
        history = pd.DataFrame({
            "Data": pd.to_datetime(["2026-09-01", "2026-09-10", "2026-08-31"]),
            "Faturamento": [1000.0, 1400.0, 9999.0],
        })
        projection = _monthly_projection(history, "2026-09-24")
        self.assertEqual(projection["elapsed_days"], 24)
        self.assertEqual(projection["remaining_days"], 6)
        self.assertEqual(projection["realized"], 2400.0)
        self.assertEqual(projection["daily_average"], 100.0)
        self.assertEqual(projection["projected_additional"], 600.0)
        self.assertEqual(projection["projected_total"], 3000.0)

    def test_monthly_activity_prefers_customer_segment_for_channels(self):
        sales = pd.DataFrame({
            "Data": pd.to_datetime(["2026-09-02", "2026-09-03"]),
            "Cliente": ["A", "B"], "Produto": ["P1", "P2"],
            "Segmento Cliente": ["INDÚSTRIA", "REVENDA"],
            "Canal": ["LEGADO", "LEGADO"],
            "Faturamento": [100.0, 200.0], "Peso": [10.0, 20.0], "Margem": [20.0, 40.0],
        })
        matrix, _ = _monthly_activity_matrix(
            sales, "Segmento Cliente", "Positivação", "2026-09-30", 1, 10
        )
        self.assertEqual(set(matrix.index), {"INDÚSTRIA", "REVENDA"})

    def test_seller_portfolio_keeps_clients_without_sales_in_both_comparison_windows(self):
        history = pd.DataFrame({
            "Data": pd.to_datetime(["2025-09-05", "2026-03-10", "2026-09-08"]),
            "Cliente": ["B", "C", "A"], "Vendedor": ["ANA"] * 3,
            "UF": ["SP"] * 3, "Município": ["Campinas"] * 3,
            "Canal": ["Direto"] * 3, "Produto": ["P1", "P2", "P3"],
            "Faturamento": [500.0, 300.0, 1000.0], "Peso": [50.0, 30.0, 100.0],
            "Margem": [50.0, 30.0, 200.0], "NF": [1, 2, 3],
        })
        current = history[history["Data"].between("2026-09-01", "2026-09-30")]
        portfolio = customer_portfolio(current, history, "2026-09-01", "2026-09-30", "year")
        self.assertEqual(set(portfolio["Cliente"]), {"A", "B", "C"})
        inactive = portfolio.set_index("Cliente").loc["C"]
        self.assertEqual(inactive["Faturamento atual"], 0)
        self.assertEqual(inactive["Faturamento referência"], 0)
        self.assertEqual(inactive["Situação"], "Sem compra no recorte")

    def test_purchase_map_keeps_inactive_portfolio_clients_as_zero_rows(self):
        history = pd.DataFrame({
            "Data": pd.to_datetime(["2024-01-05", "2026-09-08"]),
            "Cliente": ["INATIVO", "ATIVO"], "Faturamento": [500.0, 1000.0],
        })
        matrix, cadence = purchase_seasonality(history, "2026-09-30")
        self.assertIn("INATIVO", matrix.index)
        self.assertEqual(float(matrix.loc["INATIVO"].sum()), 0.0)
        self.assertEqual(set(cadence["Cliente"]), {"ATIVO", "INATIVO"})

    def test_daily_point_selection_opens_the_selected_date(self):
        event = {"selection": {"points": [{"x": "2026-09-23T00:00:00"}]}}
        self.assertEqual(_selected_plotly_date(event), pd.Timestamp("2026-09-23"))

    def test_product_page_keeps_history_when_client_has_no_current_sales(self):
        script = r'''
import pandas as pd
import streamlit as st
from src.operational_dashboard import _product_view
history = pd.DataFrame({
    "Data": pd.to_datetime(["2026-08-05"]), "Cliente": ["ALFA"],
    "Produto": ["TELHA"], "Grupo Produto": ["AÇO"], "Tipo Produto": ["LINHA"],
    "Faturamento": [1000.0], "Peso": [100.0], "Margem": [150.0], "NF": [1],
})
current = history.iloc[0:0].copy()
_product_view(
    current, history, "2026-09-01", "2026-09-30",
    lambda value: f"R$ {value:,.2f}", lambda value: f"R$ {value:,.2f}",
    lambda value: f"{value:.2%}", lambda fig: st.plotly_chart(fig),
    lambda frame, **kwargs: st.dataframe(frame), False,
)
'''
        app = AppTest.from_string(script).run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        self.assertIn("O cliente não teve produtos faturados no período atual", "\n".join(str(item.value) for item in app.info))

    def test_render_accepts_commercial_indicators_contract(self):
        self.assertIn("commercial_indicators", inspect.signature(render).parameters)
        self.assertIn("flow_events", inspect.signature(render).parameters)

    def test_metric_card_fragment_is_not_parsed_as_markdown_code(self):
        fragment = _metric_card_html("Faturamento", "R$ 1.000,00")
        self.assertNotRegex(fragment, r"(?m)^ {4}")

    def test_funnel_keeps_missing_values_distinct_from_zero(self):
        frame = _funnel_frame({"orcamentos_abertos_valor": 0, "aguardando_os_peso": 1250})
        self.assertEqual(frame.loc[frame["Etapa"] == "Orçamentos em aberto", "Cobertura"].iloc[0], "Disponível")
        self.assertIn("Orçamentos fechados", frame["Etapa"].tolist())
        self.assertIn("Orçamentos perdidos", frame["Etapa"].tolist())
        self.assertIn("Aguardando entrega", frame["Etapa"].tolist())
        self.assertEqual(frame.loc[frame["Etapa"] == "Aguardando kit", "Cobertura"].iloc[0], "Indisponível")
        self.assertEqual(frame.loc[frame["Etapa"] == "Aguardando OS", "Valor"].iloc[0], 1250)

    def test_funnel_page_renders_with_partial_snapshot(self):
        script = r'''
import pandas as pd
import streamlit as st
from src.operational_dashboard import _funnel_view
flow = pd.DataFrame({
    "Pedido": ["1"], "OP": [None], "Peso": [1000.0], "Valor": [5000.0],
    "Data Pedido": pd.to_datetime(["2026-09-02"]),
    "Data Liberação": pd.to_datetime(["2026-09-03"]),
})
_funnel_view(
    {"orcamentos_abertos_valor": 100000, "pedidos_pendentes_valor": 65000,
     "aguardando_os_peso": 12000, "aguardando_faturamento_peso": 7000},
    flow, "2026-09-01", "2026-09-30",
    lambda value: f"R$ {value:,.2f}", lambda fig: st.plotly_chart(fig),
    lambda frame, **kwargs: st.dataframe(frame), False,
)
'''
        app = AppTest.from_string(script).run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        self.assertGreaterEqual(len(app.tabs), 5)
        rendered = "\n".join(str(item.value) for item in app.markdown)
        self.assertIn("Pedidos emitidos", rendered)
        self.assertIn("Posição atual da carteira", rendered)
        self.assertIn("Pedido liberado", rendered)
        self.assertNotIn("Orçamentos em aberto</span>", rendered)

    def test_flow_uses_the_reference_date_of_each_stage(self):
        flow = pd.DataFrame({
            "Pedido": ["A", "B"], "OP": [None, None], "Peso": [100.0, 200.0], "Valor": [1000.0, 2000.0],
            "Data Orçamento": pd.to_datetime(["2026-08-31", "2026-09-10"]),
            "Data Pedido": pd.to_datetime(["2026-09-05", "2026-10-01"]),
            "Data Liberação": pd.to_datetime(["2026-09-07", "2026-10-02"]),
        })
        summary = _flow_event_summary(flow, "2026-09-01", "2026-09-30")
        counts = summary.set_index("Movimentação")["Registros"]
        self.assertEqual(counts["Orçamentos emitidos"], 1)
        self.assertEqual(counts["Pedidos emitidos"], 1)
        self.assertEqual(counts["Pedidos liberados"], 1)
        deadlines = _flow_deadlines(flow, "2026-09-01", "2026-09-30")
        self.assertEqual(deadlines.loc[deadlines["Transição"] == "Pedido → liberação", "Prazo mediano (dias)"].iloc[0], 2)

    def test_current_funnel_moves_each_order_to_one_latest_box(self):
        flow = pd.DataFrame({
            "Origem": ["Pedido liberado", "Pedido liberado", "Pedido liberado", "Pedido liberado", "Orçamento em aberto"],
            "Pedido": ["A", "A", "B", "C", "Q1"], "OP": [None] * 5,
            "Peso": [100.0, 150.0, 200.0, 300.0, 50.0],
            "Valor": [1000.0, 1500.0, 2500.0, 3500.0, 700.0],
            "Data Orçamento": pd.to_datetime([None, None, None, None, "2026-09-01"]),
            "Data Pedido": pd.to_datetime(["2026-09-02", "2026-09-02", "2026-09-03", "2026-09-04", None]),
            "Data Liberação": pd.to_datetime(["2026-09-03", "2026-09-03", "2026-09-04", "2026-09-05", None]),
            "Data OS": pd.to_datetime(["2026-09-06", None, None, None, None]),
            "Data Montagem Carga": pd.to_datetime([None] * 5),
            "Data Emissão NF": pd.to_datetime([None, None, "2026-09-07", None, None]),
            "Data Saída": pd.to_datetime([None, None, None, "2026-09-08", None]),
        })
        positions, summary = _flow_current_positions(flow)
        by_document = positions.set_index("Documento")
        self.assertEqual(by_document.loc["A", "Etapa"], "OS gerada")
        self.assertEqual(by_document.loc["B", "Etapa"], "NF emitida")
        self.assertEqual(by_document.loc["C", "Etapa"], "Saída realizada")
        self.assertEqual(by_document.loc["Q1", "Etapa"], "Orçamento em aberto")
        self.assertEqual(len(positions), 4)
        self.assertEqual(int(summary["Documentos"].sum()), 4)
        self.assertAlmostEqual(float(summary["Peso"].sum()), 800.0)
        self.assertAlmostEqual(float(by_document.loc["A", "Peso"]), 250.0)

    def test_monthly_activity_uses_net_revenue_for_positivation(self):
        sales = pd.DataFrame({
            "Data": pd.to_datetime(["2026-08-05", "2026-08-06", "2026-09-02", "2026-09-03"]),
            "Cliente": ["A", "A", "A", "B"], "Produto": ["P1", "P1", "P1", "P1"],
            "Canal": ["Varejo"] * 4, "Faturamento": [100.0, -100.0, 50.0, 75.0],
        })
        client, _ = _monthly_activity_matrix(sales, "Cliente", "Positivação", "2026-09-30", 2, 10)
        self.assertEqual(client.loc["A", pd.Timestamp("2026-08-01")], 0)
        self.assertEqual(client.loc["A", pd.Timestamp("2026-09-01")], 1)
        product, _ = _monthly_activity_matrix(sales, "Produto", "Positivação", "2026-09-30", 2, 10)
        self.assertEqual(product.loc["P1", pd.Timestamp("2026-09-01")], 2)
        revenue, _ = _monthly_activity_matrix(sales, "Canal", "Faturamento", "2026-09-30", 2, 10)
        self.assertEqual(revenue.loc["Varejo", pd.Timestamp("2026-08-01")], 0)
        self.assertEqual(revenue.loc["Varejo", pd.Timestamp("2026-09-01")], 125)

    def test_monthly_activity_calculates_weighted_price_and_margin(self):
        sales = pd.DataFrame({
            "Data": pd.to_datetime(["2026-09-02", "2026-09-03", "2026-09-04"]),
            "Cliente": ["A", "A", "B"], "Produto": ["P1", "P1", "P2"],
            "Canal": ["Varejo", "Varejo", "Varejo"],
            "Faturamento": [100.0, 300.0, 200.0], "Peso": [10.0, 20.0, 20.0],
            "Margem": [10.0, 90.0, -20.0],
        })
        price, _ = _monthly_activity_matrix(sales, "Cliente", "Preço médio/kg", "2026-09-30", 1, 10)
        margin, _ = _monthly_activity_matrix(sales, "Cliente", "Margem %", "2026-09-30", 1, 10)
        month = pd.Timestamp("2026-09-01")
        self.assertAlmostEqual(price.loc["A", month], 400 / 30)
        self.assertAlmostEqual(margin.loc["A", month], 100 / 400)
        self.assertAlmostEqual(margin.loc["B", month], -20 / 200)

    def test_monthly_activity_preserves_undefined_ratios_as_nan(self):
        sales = pd.DataFrame({
            "Data": pd.to_datetime(["2026-09-02"]), "Cliente": ["A"],
            "Produto": ["P1"], "Canal": ["Varejo"], "Faturamento": [0.0],
            "Peso": [0.0], "Margem": [0.0],
        })
        price, _ = _monthly_activity_matrix(sales, "Cliente", "Preço médio/kg", "2026-09-30", 2, 10)
        margin, _ = _monthly_activity_matrix(sales, "Cliente", "Margem %", "2026-09-30", 2, 10)
        self.assertTrue(pd.isna(price.loc["A", pd.Timestamp("2026-09-01")]))
        self.assertTrue(pd.isna(margin.loc["A", pd.Timestamp("2026-09-01")]))

    def test_municipal_map_reconciles_clients_and_unmet_potential(self):
        history = pd.DataFrame({
            "Data": pd.to_datetime(["2025-09-05", "2025-09-06", "2026-09-05", "2026-08-10"]),
            "Cliente": ["A", "B", "A", "C"], "UF": ["SP"] * 4,
            "Município": ["Campinas", "Campinas", "Campinas", "Santos"],
            "Faturamento": [1000.0, 500.0, 600.0, 200.0],
            "Peso": [100.0, 50.0, 60.0, 20.0], "Margem": [200.0, 50.0, 120.0, 30.0],
        })
        current = history[history["Data"].between("2026-09-01", "2026-09-30")]
        result = _municipal_map_data(current, history, "2026-09-01", "2026-09-30")
        campinas = result.set_index("Município").loc["Campinas"]
        self.assertEqual(campinas["Clientes totais"], 2)
        self.assertEqual(campinas["Clientes ativos"], 1)
        self.assertEqual(campinas["Potencial R$"], 1500.0)
        self.assertEqual(campinas["Potencial não atendido R$"], 900.0)
        self.assertAlmostEqual(campinas["Taxa de ativação"], .5)

    def test_municipal_map_page_renders_with_selectable_measure(self):
        script = r'''
import pandas as pd
import streamlit as st
from src.operational_dashboard import _municipal_map_view
history = pd.DataFrame({
    "Data": pd.to_datetime(["2025-09-05", "2026-09-05"]),
    "Cliente": ["A", "A"], "UF": ["SP", "SP"],
    "Município": ["Campinas", "Campinas"],
    "Faturamento": [1000.0, 600.0], "Peso": [100.0, 60.0], "Margem": [200.0, 120.0],
})
current = history[history["Data"].dt.year == 2026]
_municipal_map_view(
    current, history, "2026-09-01", "2026-09-30",
    lambda value: f"R$ {value:,.2f}", lambda value: f"R$ {value:,.2f}",
    lambda value: f"{value:.2%}", lambda fig: st.plotly_chart(fig),
    lambda frame, **kwargs: st.dataframe(frame), False,
)
'''
        app = AppTest.from_string(script).run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.selectbox[0].value, "Potencial não atendido R$")
        self.assertEqual(len(app.metric), 4)

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

    def test_assistant_renders_ready_questions(self):
        script = r'''
import pandas as pd
import streamlit as st
from src.operational_dashboard import render

sales = pd.DataFrame({
    "Data": pd.to_datetime(["2026-09-08"]), "Cliente": ["A"], "Produto": ["P1"],
    "Vendedor": ["ANA"], "Grupo Produto": ["TELHA"], "Faturamento": [1000.0],
    "Peso": [100.0], "Margem": [200.0], "NF": [1], "Cod Cliente": ["C1"],
    "Mes": [9], "UF": ["MG"], "Município": ["Betim"],
    "Benchmark Grupo": [9.0], "Preço Real Kg": [10.0],
})
render(
    sales, sales, "2026-09-01", "2026-09-30", "18/09/2026 às 15:00",
    lambda value: f"R$ {value:,.2f}", lambda value: f"R$ {value:,.2f}",
    lambda value: f"{value*100:.2f}%", lambda value: f"{value:+.2f} p.p.",
    lambda fig: st.plotly_chart(fig), lambda frame, **kwargs: st.dataframe(frame),
    permissions={"use_assistant"}, current_user={}, targets=pd.DataFrame(), target_history=sales,
)
'''
        app = AppTest.from_string(script).run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        labels = [button.label for button in app.button]
        self.assertIn("Resumo do período", labels)
        self.assertIn("Prioridades comerciais", labels)
        self.assertIn("Projeção de fechamento", labels)


if __name__ == "__main__":
    unittest.main()
