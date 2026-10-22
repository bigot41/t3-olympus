"""helper.turn_calls: the turn card's fallback, read from a Claude transcript. No T3 or network needed.

    python -m unittest discover -s tests
"""
import json, os, sys, tempfile, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import helper  # noqa: E402


def tool_use(tid, name, inp):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}}


def user_text(text, uid):
    return {"type": "user", "uuid": uid, "message": {"content": [{"type": "text", "text": text}]}}


def tool_result(tid, error):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "is_error": error}]}}


class TurnCalls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "s.jsonl")
        helper.turn_cache.clear()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, *entries, mode="a"):
        with open(self.path, mode, encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

    def test_turn_fallback_returns_calls_after_last_user_text(self):
        self.write(tool_use("t1", "mcp__olympus__update_plan", {"items": [{"content": "A", "status": "in_progress"}], "scope": "new_task"}),
                   user_text("next", "u1"),
                   tool_use("t2", "Bash", {"command": "ls"}),
                   tool_use("t3", "mcp__olympus__wrap_up", {"recap": "Done."}))
        items = helper.turn_calls(self.path)
        self.assertEqual([(i["type"], i.get("toolName")) for i in items],
                         [("dynamic_tool", "mcp__olympus__update_plan"), ("user_message", None),
                          ("dynamic_tool", "mcp__olympus__wrap_up")])
        self.assertEqual(items[2]["input"], {"recap": "Done."})
        self.assertEqual(items[2]["status"], "completed")
        # same id as T3's live item, so the two never show twice
        self.assertEqual(items[2]["id"], "turn-item:provider:claudeAgent:native-item:t3")

    def test_only_new_lines_are_read(self):
        self.write(tool_use("t1", "mcp__olympus__wrap_up", {"recap": "One."}))
        helper.turn_calls(self.path)
        offset = helper.turn_cache[self.path][0]
        self.write(tool_use("t2", "mcp__olympus__wrap_up", {"recap": "Two."}))
        calls = []
        real = helper.json.loads
        with mock.patch.object(helper.json, "loads", side_effect=lambda s: calls.append(s) or real(s)):
            items = helper.turn_calls(self.path)
        self.assertEqual(len(calls), 1)  # only the appended line was parsed
        self.assertGreater(helper.turn_cache[self.path][0], offset)
        self.assertEqual([i["input"]["recap"] for i in items], ["One.", "Two."])

    def test_half_written_line_waits(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(json.dumps(tool_use("t1", "mcp__olympus__wrap_up", {"recap": "One."})) + "\n" + '{"type": "assis')
        self.assertEqual(len(helper.turn_calls(self.path)), 1)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write('tant", "message": {"content": [{"type": "tool_use", "id": "t2", "name": "mcp__olympus__wrap_up", "input": {"recap": "Two."}}]}}\n')
        self.assertEqual(len(helper.turn_calls(self.path)), 2)

    def test_shrunk_file_is_read_again(self):
        self.write(tool_use("t1", "mcp__olympus__wrap_up", {"recap": "One."}), tool_use("t2", "mcp__olympus__wrap_up", {"recap": "Two."}))
        helper.turn_calls(self.path)
        self.write(tool_use("t9", "mcp__olympus__wrap_up", {"recap": "New."}), mode="w")
        self.assertEqual([i["input"]["recap"] for i in helper.turn_calls(self.path)], ["New."])

    def test_failed_calls_are_marked(self):
        self.write(tool_use("t1", "mcp__olympus__update_plan", {"advance": True}), tool_result("t1", True))
        self.assertEqual(helper.turn_calls(self.path)[0]["status"], "failed")

    def test_missing_file(self):
        self.assertEqual(helper.turn_calls(os.path.join(self.tmp.name, "nope.jsonl")), [])

    def test_turn_endpoint_never_throws(self):
        with mock.patch.object(helper, "session_for", side_effect=ValueError("no session")):
            self.assertEqual(helper.turn_state("x"), {"items": [], "run": None})


if __name__ == "__main__":
    unittest.main()
