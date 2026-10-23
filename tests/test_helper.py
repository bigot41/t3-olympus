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
        with mock.patch.object(helper.temporary, "session_of", return_value=None):
            self.assertEqual(helper.turn_state("x"), {"items": [], "run": None})
        with mock.patch.object(helper.temporary, "session_of", return_value="s1"),              mock.patch.object(helper, "transcript", return_value=None):
            self.assertEqual(helper.turn_state("x"), {"items": [], "run": None})


class ContinueTrust(unittest.TestCase):
    """Continue elsewhere in a folder Claude Code doesn't trust: ask first, trust only that folder, retry."""
    NO = mock.Mock(stdout="", stderr=r"Workspace not trusted. Run `claude` in C:\work\repo once and accept the trust prompt, then retry.")
    OK = mock.Mock(stdout="backgrounded · ab12cd34 (idle)", stderr="")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = os.path.join(self.tmp.name, ".claude.json")
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump({"projects": {"C:/other": {"x": 1}}}, f)
        for p in (mock.patch.object(helper, "CLAUDE_JSON", self.cfg),
                  mock.patch.object(helper, "session_for", return_value=("s1", "C:/work/repo", "Chat")),
                  mock.patch.object(helper, "remote_url", return_value=None)):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def run_with(self, allow, *outs):
        agents = mock.Mock(stdout="[]")
        with mock.patch.object(helper, "claude", side_effect=[agents, *outs]) as c:
            return helper.continue_elsewhere("t1", allow), c

    def test_asks_before_trusting(self):
        res, _ = self.run_with(False, self.NO)
        self.assertEqual(res["trust"], r"C:\work\repo")
        self.assertNotIn("C:/work/repo", json.loads(open(self.cfg, encoding="utf-8").read())["projects"])

    def test_allow_trusts_the_named_folder_and_retries(self):
        res, c = self.run_with(True, self.NO, self.OK)
        self.assertEqual(res["id"], "ab12cd34")
        self.assertEqual(c.call_count, 3)
        projects = json.loads(open(self.cfg, encoding="utf-8").read())["projects"]
        self.assertTrue(projects["C:/work/repo"]["hasTrustDialogAccepted"])
        self.assertEqual(projects["C:/other"], {"x": 1})


if __name__ == "__main__":
    unittest.main()


class PetsToggle(unittest.TestCase):
    """Hide pets / Ctrl+Alt+P: off stays off (the helper doesn't restart them), on starts them now."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        off = os.path.join(self.tmp.name, "local", "pets-off")
        for patch in (mock.patch.object(helper, "PETS_OFF", off), mock.patch.object(helper.subprocess, "Popen")):
            self.addCleanup(patch.stop)
            patch.start()
        self.popen = helper.subprocess.Popen
        helper.pets_checked = 0.0

    def tearDown(self):
        self.tmp.cleanup()

    def test_off_then_on(self):
        self.assertEqual(helper.pets_toggle(), {"on": False})
        self.assertTrue(os.path.exists(helper.PETS_OFF))
        self.assertEqual(helper.pets_toggle(), {"on": True})
        self.assertFalse(os.path.exists(helper.PETS_OFF))

    def test_turning_on_starts_them_at_once(self):
        helper.pets_toggle()
        helper.pets_checked = 1e12  # just checked: only the toggle's own reset lets it start them
        with mock.patch.object(helper.socket, "socket") as sock:
            helper.pets_toggle()
        sock.assert_called_once()
        self.popen.assert_called_once()

    def test_off_means_no_restart(self):
        helper.pets_toggle()
        helper.ensure_pets()
        self.popen.assert_not_called()
