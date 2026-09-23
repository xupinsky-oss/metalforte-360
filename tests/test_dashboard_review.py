import unittest

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from src.analytics import group_metrics
from src.commercial_intelligence import entity_comparison
from src.operational_dashboard import (
    _municipal_color_settings,
    _municipal_coordinates,
    _municipal_geojson,
)


class DashboardLogicReviewTests(unittest.TestCase):
    def test_municipal_reference_links_ibge_codes_to_polygons(self):
        coordinates = _municipal_coordinates()
        campinas = coordinates[
            (coordinates["_municipio_key"] == "CAMPINAS") & (coordinates["UF"] == "SP")
        ].iloc[0]
        self.assertEqual(campinas["Código IBGE"], "3509502")
        polygon_ids = {
            str(feature["properties"]["id"])
            for feature in _municipal_geojson()["features"]
        }
        self.assertIn("3509502", polygon_ids)
        self.assertGreater(len(polygon_ids), 5500)

    def test_municipal_palette_is_visible_and_resistant_to_outliers(self):
        frame = pd.DataFrame({"Faturamento": [0.0, 10.0, 20.0, 30.0, 10000.0]})
        scale, color_range, midpoint = _municipal_color_settings(frame, "Faturamento")
        self.assertNotIn(scale[0][1].upper(), {"#FFFFFF", "#FFF0E8", "#F7F9FC"})
        self.assertLess(color_range[1], frame["Faturamento"].max())
        self.assertIsNone(midpoint)

    def test_margin_palette_is_symmetric_around_zero(self):
        frame = pd.DataFrame({"Margem %": [-.20, -.05, .10, .30]})
        _, color_range, midpoint = _municipal_color_settings(frame, "Margem %")
        self.assertAlmostEqual(abs(color_range[0]), color_range[1])
        self.assertEqual(midpoint, 0)

    def test_undefined_ratios_are_not_presented_as_measured_zero(self):
        current = pd.DataFrame({
            "Produto": ["SEM BASE"], "Faturamento": [0.0], "Peso": [0.0],
            "Margem": [0.0], "NF": [1], "Cliente": ["A"],
        })
        comparison = entity_comparison(current, current.iloc[0:0], "Produto").iloc[0]
        summary = group_metrics(current, "Produto").iloc[0]
        self.assertTrue(np.isnan(comparison["Margem % atual"]))
        self.assertTrue(np.isnan(comparison["Preço médio atual"]))
        self.assertTrue(np.isnan(summary["margem_pct"]))
        self.assertTrue(np.isnan(summary["preco_kg"]))


class DashboardPageSmokeTests(unittest.TestCase):
    @staticmethod
    def _script(permission):
        return f'''
import pandas as pd
import streamlit as st
import src.auth as auth
from src.operational_dashboard import render

auth.list_users = lambda: [{{
    "id": "review-user", "email": "review@example.com",
    "user_metadata": {{"display_name": "Usuário de revisão"}},
    "app_metadata": {{"mf_role": "viewer", "mf_permissions": ["view_overview"]}},
    "last_sign_in_at": None,
}}]

history = pd.DataFrame({{
    "Data": pd.to_datetime(["2025-09-05", "2026-08-10", "2026-09-05", "2026-09-12"]),
    "Cliente": ["CLIENTE A", "CLIENTE B", "CLIENTE A", "CLIENTE B"],
    "Produto": ["P1", "P2", "P1", "P2"], "Vendedor": ["ANA", "BRUNO", "ANA", "BRUNO"],
    "Grupo Produto": ["TELHA", "TUBO", "TELHA", "TUBO"],
    "Tipo Produto": ["A", "B", "A", "B"], "Segmento Cliente": ["IND", "REV", "IND", "REV"],
    "Faturamento": [1000.0, 500.0, 600.0, 900.0], "Peso": [100.0, 50.0, 60.0, 90.0],
    "Margem": [200.0, 75.0, 120.0, 135.0], "NF": [1, 2, 3, 4],
    "Cod Cliente": ["A", "B", "A", "B"], "Mes": [9, 8, 9, 9],
    "UF": ["SP", "SP", "SP", "SP"], "Município": ["Campinas", "Santos", "Campinas", "Santos"],
    "Canal": ["Direto", "Revenda", "Direto", "Revenda"], "Filial": ["01", "01", "01", "01"],
    "Espessura": [1.0, 2.0, 1.0, 2.0], "Benchmark Grupo": [9.0, 9.0, 9.0, 9.0],
    "Preço Real Kg": [10.0, 10.0, 10.0, 10.0],
}})
current = history[history["Data"].between("2026-09-01", "2026-09-30")]
targets = pd.DataFrame({{
    "Competência": pd.to_datetime(["2026-09-01", "2026-09-01"]),
    "Vendedor": ["ANA", "BRUNO"], "Grupo Produto": ["TELHA", "TUBO"],
    "Meta R$": [1200.0, 1000.0], "Meta KG": [120.0, 100.0],
}})
flow = pd.DataFrame({{
    "Origem": ["Pedido liberado"], "Pedido": ["PED-1"], "OP": ["OP-1"],
    "Peso": [100.0], "Valor": [1000.0],
    "Data Orçamento": pd.to_datetime(["2026-09-01"]), "Data Pedido": pd.to_datetime(["2026-09-02"]),
    "Data Liberação": pd.to_datetime(["2026-09-03"]), "Data OS": pd.to_datetime(["2026-09-04"]),
    "Data Montagem Carga": pd.to_datetime([None]), "Data Emissão NF": pd.to_datetime([None]),
    "Data Saída": pd.to_datetime([None]),
}})
brl = lambda value: f"R$ {{value:,.2f}}"
pct = lambda value: f"{{value:.2%}}"
render(
    current, history, "2026-09-01", "2026-09-30", "23/09/2026 às 07:00",
    brl, brl, pct, lambda value: f"{{value:+.2f}} p.p.",
    lambda fig: st.plotly_chart(fig), lambda frame, **kwargs: st.dataframe(frame),
    permissions=set([{permission!r}]), current_user={{}}, targets=targets, target_history=history,
    target_filters={{}}, commercial_indicators={{
        "orcamentos_abertos_valor": 1000.0, "pedidos_pendentes_valor": 800.0,
        "aguardando_os_peso": 100.0, "aguardando_faturamento_peso": 50.0,
    }}, flow_events=flow,
)
'''

    def test_every_reader_page_opens_without_runtime_error(self):
        permissions = [
            "view_overview", "view_clients", "view_products", "view_daily", "view_sellers",
            "view_targets", "view_funnel", "view_map", "view_heatmap", "view_insights",
            "view_pivot", "view_yoy", "use_assistant",
            "manage_users",
        ]
        for permission in permissions:
            with self.subTest(permission=permission):
                app = AppTest.from_string(self._script(permission)).run(timeout=30)
                self.assertEqual(list(app.exception), [])


if __name__ == "__main__":
    unittest.main()
