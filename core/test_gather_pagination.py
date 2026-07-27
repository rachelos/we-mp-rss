import ast
import unittest
from pathlib import Path

from core.gather_pagination import (
    DEFAULT_CATCH_UP_MAX_PAGES,
    HARD_CATCH_UP_MAX_PAGES,
    normalize_catch_up_max_pages,
    should_stop_after_page,
)


class PaginationTest(unittest.TestCase):
    def test_normalize_uses_default_for_invalid_value(self):
        self.assertEqual(
            normalize_catch_up_max_pages("invalid"),
            DEFAULT_CATCH_UP_MAX_PAGES,
        )

    def test_normalize_clamps_page_range(self):
        self.assertEqual(normalize_catch_up_max_pages(0), 1)
        self.assertEqual(
            normalize_catch_up_max_pages(999),
            HARD_CATCH_UP_MAX_PAGES,
        )

    def test_stop_after_page_when_existing_article_is_seen(self):
        self.assertTrue(should_stop_after_page([True, False, True], True))

    def test_continue_when_page_only_contains_new_articles(self):
        self.assertFalse(should_stop_after_page([True, True], True))

    def test_manual_pagination_ignores_existing_articles(self):
        self.assertFalse(should_stop_after_page([False], False))

    def test_all_gather_models_wire_automatic_stop(self):
        root = Path(__file__).resolve().parent
        for model_name in ("web", "app", "api"):
            source = (root / "wx/model" / f"{model_name}.py").read_text(
                encoding="utf-8"
            )
            tree = ast.parse(source)
            get_articles = next(
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
                and node.name == "get_Articles"
            )
            argument_names = [argument.arg for argument in get_articles.args.args]
            called_functions = {
                ast.unparse(node.func)
                for node in ast.walk(get_articles)
                if isinstance(node, ast.Call)
            }

            self.assertIn("StopOnExisting", argument_names)
            self.assertIn("should_stop_after_page", called_functions)

    def test_scheduler_enables_catch_up_mode(self):
        root = Path(__file__).resolve().parent
        source = (root.parent / "jobs/mps.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        get_article_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get_Articles"
        ]

        self.assertTrue(
            any(
                any(
                    keyword.arg == "StopOnExisting"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                    for keyword in call.keywords
                )
                for call in get_article_calls
            )
        )


if __name__ == "__main__":
    unittest.main()
