import unittest

from app.helpdesk.texts.formatters import format_ru_phone


class TextFormatterTests(unittest.TestCase):
    def test_format_ru_phone(self) -> None:
        cases = {
            None: "не указан",
            "": "не указан",
            "79530853578": "+79530853578",
            "+79530853578": "+79530853578",
            "89530853578": "+79530853578",
            "9530853578": "+79530853578",
            "+7 (953) 085-35-78": "+79530853578",
            "abc": "не указан",
        }

        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(format_ru_phone(raw), expected)


if __name__ == "__main__":
    unittest.main()
