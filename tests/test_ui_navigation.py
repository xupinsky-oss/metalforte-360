import unittest

from src.ui.navigation import group_pages


class NavigationTests(unittest.TestCase):
    def test_groups_keep_page_order_and_never_add_unavailable_pages(self):
        pages = [
            ("Command Center", "view_overview"),
            ("Clientes", "view_clients"),
            ("Estoque", "view_stock"),
            ("Administração", "manage_users"),
        ]

        grouped = group_pages(pages)

        self.assertEqual(list(grouped), ["Visão geral", "Comercial", "Operações", "Administração"])
        self.assertEqual([page for entries in grouped.values() for page in entries], pages)

    def test_unknown_page_is_kept_in_fallback_group(self):
        pages = [("Nova tela", "view_new_page")]
        self.assertEqual(group_pages(pages), {"Outras visões": pages})


if __name__ == "__main__":
    unittest.main()
