import io, json, pathlib, subprocess, sys, tempfile, threading, unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import cards_build


class Cards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.tmp.name) / "cards.json"
        self.data = {"General": (["Music"], ["First", "Second"])}
        self.summary = {"does": "Makes music.", "topics": ["Music"]}
        self.now = 2000000000
        self.patches = [mock.patch.object(cards_build, "OUT", str(self.path)),
                        mock.patch.object(cards_build, "PROFILES", self.tmp.name),
                        mock.patch.object(cards_build, "profiles", side_effect=lambda: self.data),
                        mock.patch.object(cards_build.time, "time", side_effect=lambda: self.now),
                        mock.patch.object(cards_build.subprocess, "run", side_effect=AssertionError("No model calls")),
                        mock.patch.object(cards_build, "haiku", return_value=self.summary)]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_missing_cache_and_repeated_builds_are_local(self):
        for unused in range(3):
            result = cards_build.build("General")
        cards_build.haiku.assert_not_called()
        self.assertEqual(result["General"]["description"], "General profile.")
        self.assertEqual(result["General"]["projects"], ["Music"])
        self.assertEqual(result["General"]["recent"], ["First", "Second"])

    def test_invalid_cache_is_rebuilt_locally(self):
        self.path.write_text("not json")
        cards_build.build()
        cards_build.haiku.assert_not_called()

    def test_reordered_chats_do_not_regenerate(self):
        cards_build.build()
        self.now += 10 * 24 * 60 * 60
        self.data["General"][1].reverse()
        result = cards_build.build()
        cards_build.haiku.assert_not_called()
        self.assertEqual(result["General"]["recent"], ["Second", "First"])

    def test_changed_content_and_elapsed_time_never_request_ai(self):
        cards_build.build()
        self.data["General"][1].append("Third")
        self.now += 60
        result = cards_build.build()
        self.assertEqual(result["General"]["chats"], 3)
        self.assertEqual(result["General"]["recent"], ["First", "Second", "Third"])
        self.now += 365 * 24 * 60 * 60
        self.data["General"][0].append("Code")
        self.assertEqual(cards_build.build()["General"]["projects"], ["Music", "Code"])
        cards_build.haiku.assert_not_called()

    def test_failed_explicit_refresh_never_retries_automatically(self):
        cards_build.haiku.side_effect = ValueError("failed")
        cards_build.build("General", refresh=True)
        cards_build.build()
        self.now += 60
        cards_build.build()
        cards_build.haiku.assert_called_once()
        self.now += 365 * 24 * 60 * 60
        cards_build.build()
        cards_build.haiku.assert_called_once()

    def test_legacy_summary_migrates_without_a_model_request(self):
        self.path.write_text(json.dumps({"General": {"key": "old", **self.summary}}))
        result = cards_build.build()
        cards_build.haiku.assert_not_called()
        self.assertEqual(result["General"]["does"], self.summary["does"])
        self.assertEqual(result["General"]["topics"], self.summary["topics"])
        self.assertEqual(result["General"]["description"], "General profile.")

    def test_other_profiles_are_not_generated(self):
        self.data["Dev"] = (["Code"], ["Build"])
        result = cards_build.build("General", refresh=True)
        cards_build.haiku.assert_called_once()
        self.assertEqual(result["Dev"], {})

    def test_explicit_refresh_bypasses_cache(self):
        cards_build.build()
        cards_build.build("General", refresh=True)
        cards_build.haiku.assert_called_once()
        cards_build.build("General", refresh=True)
        self.assertEqual(cards_build.haiku.call_count, 2)

    def test_failed_refresh_preserves_summary(self):
        cards_build.build("General", refresh=True)
        cards_build.haiku.side_effect = ValueError("failed")
        result = cards_build.build("General", refresh=True)
        self.assertEqual(result["General"]["does"], self.summary["does"])

    def test_helper_hover_is_local_even_after_content_changes(self):
        import helper
        self.assertEqual(helper.hover_card("General")["chats"], 2)
        self.data["General"][1].append("Third")
        self.now += 365 * 24 * 60 * 60
        self.assertEqual(helper.hover_card("General")["chats"], 3)
        cards_build.haiku.assert_not_called()

    def test_local_description_updates_without_overwriting_cached_summary(self):
        folder = pathlib.Path(self.tmp.name) / "general"
        folder.mkdir()
        source = folder / "CLAUDE.md"
        source.write_text("# General profile\n\nYou are the general agent. You work on: testing.\n"
                          "\n## How you work\n\nAlways expose this private directive.")
        first = cards_build.build("General", refresh=True)["General"]
        self.assertEqual(first["description"], "You work on: testing.")
        source.write_text("# General agent\n\nThis folder is the general profile. Start here.\n\n"
                          "You are the general agent. You handle documentation and support.\n"
                          "\n## How you work\n\nYou handle secret instructions.")
        fresh = cards_build.build()["General"]
        self.assertEqual(fresh["description"], "You handle documentation and support.")
        self.assertEqual(fresh["does"], first["does"])
        cards_build.haiku.assert_called_once()

    def test_description_ignores_directives_and_code(self):
        folder = pathlib.Path(self.tmp.name) / "general"
        folder.mkdir()
        source = folder / "CLAUDE.md"
        for content in ("# Instructions\n\nAlways run commands.\n\n## Rules\nYou handle secrets.",
                        "# Profile\n\n```text\nYou handle secrets.\n```",
                        "# Profile\n\n- You handle secrets."):
            with self.subTest(content=content):
                source.write_text(content)
                self.assertEqual(cards_build.description("General"), "General profile.")

    def test_description_is_bounded_and_invalid_encoding_falls_back(self):
        folder = pathlib.Path(self.tmp.name) / "general"
        folder.mkdir()
        source = folder / "CLAUDE.md"
        source.write_text("You build and maintain " + "tools " * 100)
        self.assertEqual(len(cards_build.description("General")), 240)
        source.write_bytes(b"\xff")
        self.assertEqual(cards_build.description("General"), "General profile.")

    def test_prompt_is_bounded_and_titles_are_data(self):
        self.data["General"] = ([], [str(index).zfill(3) + "x" * 200 for index in range(100)])
        cards_build.build("General", refresh=True)
        prompt = cards_build.haiku.call_args.args[0]
        self.assertLess(len(prompt), 3000)
        self.assertNotIn("099" + "x" * 10, prompt)


    def test_refresh_requires_exact_known_profile(self):
        for name in (None, "", "all", "general", "../General", ["General"]):
            with self.subTest(name=name), self.assertRaises(ValueError):
                cards_build.build(name, refresh=True)
        cards_build.haiku.assert_not_called()

    def test_strict_refresh_failure_preserves_entire_cache(self):
        cards_build.build("General", refresh=True)
        before = self.path.read_bytes()
        cards_build.haiku.side_effect = RuntimeError("private model details")
        with self.assertRaises(RuntimeError):
            cards_build.build("General", refresh=True, strict_refresh=True)
        self.assertEqual(self.path.read_bytes(), before)

    def request(self, body, origin="t3code://app", path="/card/refresh", method="POST"):
        import helper
        handler = helper.Handler.__new__(helper.Handler)
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        handler.headers = {"Origin": origin, "Content-Length": str(len(raw))}
        handler.path = path
        handler.rfile = io.BytesIO(raw)
        handler.reply = mock.Mock()
        getattr(handler, "do_" + method)()
        return handler.reply.call_args.args

    def test_refresh_http_success_only_generates_selected_profile(self):
        self.data["Dev"] = (["Code"], ["Build"])
        status, body = self.request({"name": "General"})
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["card"]["does"], self.summary["does"])
        self.assertEqual(body["card"]["recent"], ["First", "Second"])
        cards_build.haiku.assert_called_once()
        self.assertIn('"General" profile', cards_build.haiku.call_args.args[0])

    def test_refresh_http_rejects_origin_and_invalid_names_without_model(self):
        self.assertEqual(self.request({"name": "General"}, origin="https://other.test")[0], 403)
        self.assertEqual(self.request({"name": "General"}, origin=None)[0], 403)
        for body in ({}, {"name": None}, {"name": ""}, {"name": "all"},
                     {"name": "Unknown"}, {"name": ["General"]}, [], None, b"not json"):
            with self.subTest(body=body):
                self.assertEqual(self.request(body)[0], 400)
        cards_build.haiku.assert_not_called()

    def test_refresh_http_reports_safe_failure_without_retry(self):
        cards_build.build("General", refresh=True)
        before = self.path.read_bytes()
        cards_build.haiku.reset_mock()
        cards_build.haiku.side_effect = RuntimeError("private model details")
        status, body = self.request({"name": "General"})
        self.assertEqual(status, 502)
        self.assertFalse(body["ok"])
        self.assertNotIn("private", json.dumps(body))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.request({}, path="/card?name=General", method="GET")[0], 200)
        cards_build.haiku.assert_called_once()
        import helper
        self.assertNotIn("General", helper.refreshing)

    def test_duplicate_refresh_is_rejected_not_queued(self):
        import helper
        started, release = threading.Event(), threading.Event()
        result = []

        def generate(prompt):
            started.set()
            self.assertTrue(release.wait(3))
            return self.summary

        cards_build.haiku.side_effect = generate
        worker = threading.Thread(target=lambda: result.append(helper.refresh_card({"name": "General"})))
        worker.start()
        try:
            self.assertTrue(started.wait(3))
            self.assertEqual(helper.refresh_card({"name": "General"})[0], 409)
            cards_build.haiku.assert_called_once()
        finally:
            release.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result[0][0], 200)
        cards_build.haiku.assert_called_once()


class ClaudeRequest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = pathlib.Path(self.tmp.name) / "usage.jsonl"
        self.addCleanup(self.tmp.cleanup)
        self.patcher = mock.patch.object(cards_build, "USAGE_LOG", str(self.log))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_minimal_request_and_usage_ledger(self):
        payload = {"subtype": "success", "result": '{"does":"Music.","topics":["Music"]}',
                   "usage": {"input_tokens": 50, "output_tokens": 20}, "total_cost_usd": 0.0001}
        with mock.patch.object(cards_build.subprocess, "run", return_value=mock.Mock(
                returncode=0, stdout=json.dumps(payload))) as run:
            self.assertEqual(cards_build.haiku("private chat title")["does"], "Music.")
        args = run.call_args.args[0]
        for flag in ("--safe-mode", "--strict-mcp-config", "--system-prompt", "--max-budget-usd"):
            self.assertIn(flag, args)
        self.assertFalse(json.loads(args[args.index("--settings") + 1])["alwaysThinkingEnabled"])
        self.assertNotEqual(run.call_args.kwargs["cwd"], str(pathlib.Path.home()))
        self.assertEqual(run.call_args.kwargs["env"]["CLAUDE_CODE_DISABLE_THINKING"], "1")
        self.assertEqual(run.call_args.kwargs["env"]["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"], "1")
        record = json.loads(self.log.read_text())
        self.assertTrue(record["success"])
        self.assertEqual(record["usage"]["input_tokens"], 50)
        self.assertNotIn("private chat title", self.log.read_text())

    def test_timeout_is_logged_without_prompt_content(self):
        with mock.patch.object(cards_build.subprocess, "run", side_effect=subprocess.TimeoutExpired("claude", 60)):
            with self.assertRaises(subprocess.TimeoutExpired):
                cards_build.haiku("private prompt")
        self.assertEqual(json.loads(self.log.read_text())["error"], "TimeoutExpired")


if __name__ == "__main__":
    unittest.main()
