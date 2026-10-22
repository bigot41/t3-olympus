"""Tests for the olympus MCP server rules (shared cases in turn_cases.json)."""
import io, json, os, sys, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import wrapup_mcp as w

CASES = json.load(open(os.path.join(os.path.dirname(__file__), "turn_cases.json"), encoding="utf-8"))


def call(name, args, id=1):
    return {"jsonrpc": "2.0", "id": id, "method": "tools/call", "params": {"name": name, "arguments": args}}


def run_server(*msgs):
    out = io.StringIO()
    with mock.patch.object(sys, "stdin", io.StringIO("".join(json.dumps(m) + "\n" for m in msgs))), \
            mock.patch.object(sys, "stdout", out):
        w.serve()
    return [json.loads(l) for l in out.getvalue().splitlines()]


class WrapUp(unittest.TestCase):
    def test_cases(self):
        for c in CASES["wrap_up"]:
            with self.subTest(c["name"]):
                card = w.normalize_wrap_up(c["input"])
                card.pop("advice")
                self.assertEqual(card, c["card"])
                self.assertEqual(bool(w.shows_box(card)), c["box"])

    def test_advice_on_trim(self):
        card = w.normalize_wrap_up({"recap": "r", "ask": "a", "actions": [{"label": "A"}, {"label": "B"}, {"label": "C"}]})
        self.assertTrue(card["advice"])

    def test_missing_recap_is_error(self):
        res = run_server(call("wrap_up", {"ask": "x"}))[0]["result"]
        self.assertTrue(res["isError"])

    def test_wrap_up_call_ok(self):
        res = run_server(call("wrap_up", {"recap": "Done."}))[0]["result"]
        self.assertFalse(res.get("isError"))

    def test_unknown_tool_is_error(self):
        self.assertTrue(run_server(call("nope", {}))[0]["result"]["isError"])


class Plan(unittest.TestCase):
    def test_cases(self):
        for c in CASES["plan"]:
            with self.subTest(c["name"]):
                steps, text, _ = w.apply_plan(c["steps"], c["args"])
                self.assertEqual(steps, c["after"])
                self.assertTrue(text)

    def test_items_need_scope(self):
        before = [{"content": "a", "status": "pending"}]
        steps, text, _ = w.apply_plan(before, {"items": [{"content": "b", "status": "pending"}]})
        self.assertEqual(steps, before)
        self.assertIn("scope", text)

    def test_two_in_progress_warns(self):
        _, text, _ = w.apply_plan(None, {"scope": "first_task", "items": [
            {"content": "a", "status": "in_progress"}, {"content": "b", "status": "in_progress"}]})
        self.assertIn("one step", text)

    def test_advance_without_plan_asks_for_items(self):
        _, text, _ = w.apply_plan(None, {"advance": True})
        self.assertIn("items", text)

    def test_bad_step_number_changes_nothing(self):
        before = [{"content": "a", "status": "pending"}]
        steps, text, _ = w.apply_plan(before, {"done": [5]})
        self.assertEqual(steps, before)
        self.assertIn("Nothing changed", text)

    def test_server_keeps_plan(self):
        r = run_server(
            call("update_plan", {"scope": "first_task", "items": [
                {"content": "a", "status": "in_progress"}, {"content": "b", "status": "pending"}]}),
            call("update_plan", {"advance": True}, 2))
        self.assertIn("Step 2 of 2", r[1]["result"]["content"][0]["text"])
        self.assertFalse(r[1]["result"].get("isError"))

    def test_empty_call_is_error(self):
        self.assertTrue(run_server(call("update_plan", {}))[0]["result"]["isError"])


class Init(unittest.TestCase):
    def test_initialize_has_instructions(self):
        r = run_server({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                       {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        ins = r[0]["result"]["instructions"]
        self.assertTrue(ins)
        self.assertIn("update_plan", ins)
        self.assertIn("wrap_up", ins)
        self.assertEqual({t["name"] for t in r[1]["result"]["tools"]}, {"update_plan", "wrap_up"})


if __name__ == "__main__":
    unittest.main()
