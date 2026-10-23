import io, json, pathlib, sys, unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import title_request


def response(subtype, result=None, success=True):
    return json.dumps({"type": "control_response", "response": {
        "request_id": subtype, "subtype": "success" if success else "error",
        "response": {} if result is None else result}}) + "\n"


class TitleRequest(unittest.TestCase):
    def run_fake(self, output, description="Fix sidebar layout", wait_error=None):
        process = mock.Mock()
        process.stdin = io.StringIO()
        process.stdout = io.StringIO(output)
        process.poll.return_value = None
        process.wait.side_effect = wait_error
        written = []
        process.stdin.close = lambda: written.extend(process.stdin.getvalue().splitlines())
        with mock.patch.object(title_request.subprocess, "Popen", return_value=process) as spawn:
            title = title_request.generate(description)
        return title, [json.loads(line) for line in written], spawn, process

    def test_dedicated_control_without_chat_turn(self):
        title, packets, spawn, process = self.run_fake(
            response("initialize") + response("generate_session_title", {"title": "Sidebar layout"}))
        self.assertEqual(title, "Sidebar layout")
        self.assertEqual([packet["type"] for packet in packets], ["control_request"] * 2)
        self.assertEqual(packets[1]["request"], {"subtype": "generate_session_title",
                         "description": "Fix sidebar layout", "persist": False})
        spawn.assert_called_once()
        options = spawn.call_args.kwargs
        self.assertEqual(options["env"]["CLAUDE_CODE_MAX_OUTPUT_TOKENS"], "200")
        self.assertEqual(options["env"]["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"], "1")
        self.assertFalse(pathlib.Path(options["cwd"]).exists())
        process.kill.assert_called_once()
        process.wait.assert_called_once()

    def test_input_and_title_bounds(self):
        title, packets, unused, process = self.run_fake(
            response("initialize") + response("generate_session_title", {"title": "x" * 81}), "word " * 600)
        self.assertEqual(len(packets[1]["request"]["description"]), 2000)
        self.assertEqual(title, " ".join(["word"] * 8))

    def test_errors_fall_back_without_retries(self):
        outputs = ["", "not json\n", response("initialize", success=False),
                   response("initialize") + response("generate_session_title", []),
                   response("initialize") + response("generate_session_title", {"title": "bad\ntitle"}),
                   '{"type":"control_response","response":[]}\n',
                   '{"type":"control_request"}\n']
        for output in outputs:
            with self.subTest(output=output):
                title, packets, spawn, process = self.run_fake(output)
                self.assertEqual(title, "Fix sidebar layout")
                spawn.assert_called_once()

    def test_spawn_failure_and_empty_input(self):
        with mock.patch.object(title_request.subprocess, "Popen", side_effect=OSError) as spawn:
            self.assertEqual(title_request.generate("Fix layout"), "Fix layout")
            spawn.assert_called_once()
            spawn.reset_mock()
            self.assertEqual(title_request.generate("  "), "New chat")
            spawn.assert_not_called()

    def test_cleanup_failure_does_not_replace_result(self):
        title, unused, spawn, process = self.run_fake(
            response("initialize") + response("generate_session_title", {"title": "Layout"}),
            wait_error=title_request.subprocess.TimeoutExpired("claude", 2))
        self.assertEqual(title, "Layout")


if __name__ == "__main__":
    unittest.main()
