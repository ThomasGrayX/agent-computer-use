import unittest

from ai_cursor.json_utils import extract_json_object


class ExtractJsonObjectTests(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(extract_json_object('{"action":"done"}'), {"action": "done"})

    def test_fenced_json(self):
        self.assertEqual(
            extract_json_object('```json\n{"action":"wait","seconds":1}\n```'),
            {"action": "wait", "seconds": 1},
        )

    def test_text_around_json(self):
        self.assertEqual(
            extract_json_object('Here is the action: {"action":"click","x":1,"y":2} ok'),
            {"action": "click", "x": 1, "y": 2},
        )


if __name__ == "__main__":
    unittest.main()
