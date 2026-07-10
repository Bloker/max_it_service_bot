import unittest

from app.helpdesk.services.jamaica_seed_data import JAMAICA_ISSUE_CATEGORIES
from scripts.seed_jamaica_knowledge_base_test_data import SCOPE_SEED_ITEMS, SEED_ITEMS


class JamaicaKnowledgeBaseSeedTests(unittest.TestCase):
    def test_seed_items_cover_all_jamaica_category_codes(self) -> None:
        expected_codes = {category.code for category in JAMAICA_ISSUE_CATEGORIES}
        seed_codes = {code for code, _, _, _ in SEED_ITEMS}

        self.assertEqual(seed_codes, expected_codes)

    def test_scope_seed_contains_expected_scope_codes(self) -> None:
        scope_codes = [code for code, _, _, _ in SCOPE_SEED_ITEMS]

        self.assertEqual(
            scope_codes,
            ["jamaica", "general_it", "infrastructure", "systems"],
        )


if __name__ == "__main__":
    unittest.main()
