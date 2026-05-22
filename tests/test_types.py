import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_cursor.cli import _load_env_file
from ai_cursor.providers import parse_model_spec
from ai_cursor.types import ActionDecision


class ActionDecisionTests(unittest.TestCase):
    def test_coordinate_coercion(self):
        decision = ActionDecision.from_dict({"action": "click", "x": "10.2", "y": 20.8})
        self.assertEqual(decision.action, "click")
        self.assertEqual(decision.x, 10)
        self.assertEqual(decision.y, 21)

    def test_unknown_action_becomes_noop(self):
        decision = ActionDecision.from_dict({"action": "dance"})
        self.assertEqual(decision.action, "noop")

    def test_click_type_alias_and_clear(self):
        decision = ActionDecision.from_dict(
            {"action": "click_and_type", "x": 1, "y": 2, "text": "hello", "clear": "true"}
        )
        self.assertEqual(decision.action, "click_type")
        self.assertEqual(decision.x, 1)
        self.assertEqual(decision.y, 2)
        self.assertEqual(decision.text, "hello")
        self.assertTrue(decision.clear)

    def test_keyboard_aliases(self):
        self.assertEqual(ActionDecision.from_dict({"action": "input_text", "text": "hi"}).action, "type")
        self.assertEqual(ActionDecision.from_dict({"action": "hotkey", "key": "ctrl+l"}).action, "key")

    def test_drag_aliases_and_finished_state(self):
        decision = ActionDecision.from_dict(
            {
                "action": "drag",
                "x": 10,
                "y": 20,
                "end_x": "300.2",
                "end_y": "400.8",
                "duration": "1.2",
                "screen_state": "Desktop with the icon moved to the right.",
                "available": ["moved icon", "desktop"],
            }
        )
        self.assertEqual(decision.action, "drag")
        self.assertEqual(decision.to_x, 300)
        self.assertEqual(decision.to_y, 401)
        self.assertEqual(decision.duration, 1.2)
        self.assertEqual(decision.available, ["moved icon", "desktop"])

    def test_model_spec(self):
        spec = parse_model_spec("anthropic:opus-4.7")
        self.assertEqual(spec.provider, "anthropic")
        self.assertEqual(spec.model, "opus-4.7")

    def test_load_env_file(self):
        with TemporaryDirectory() as temp_dir, patch.dict("os.environ", {}, clear=True):
            env_path = Path(temp_dir) / ".env"
            env_path.write_text('OPENAI_API_KEY="abc123"\nAI_CURSOR_MODEL=openai:gpt-5.5\n', encoding="utf-8")
            _load_env_file(env_path)
            from os import environ

            self.assertEqual(environ["OPENAI_API_KEY"], "abc123")
            self.assertEqual(environ["AI_CURSOR_MODEL"], "openai:gpt-5.5")


if __name__ == "__main__":
    unittest.main()
