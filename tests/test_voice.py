"""Dictation: how the speech service's messages become text. No network, no microphone.

    python -m unittest discover tests
"""
import json, os, sys, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import voice  # noqa: E402


class FakeSocket:
    def __init__(self, messages):
        self.messages, self.sent = [json.dumps(m) for m in messages], []

    def send(self, data, text=False):
        self.sent.append(data)

    def recv(self):
        return self.messages.pop(0) if self.messages else None

    def close(self):
        pass


def run(messages):
    d = voice.Dictation.__new__(voice.Dictation)
    d.final, d.interim, d.error, d.done = [], "", None, False
    d.ws = FakeSocket(messages)
    d._listen()
    return d


class Transcript(unittest.TestCase):
    def test_each_message_replaces_the_phrase_until_it_ends(self):
        d = run([{"type": "TranscriptInterim", "data": "Please"}, {"type": "TranscriptText", "data": "Please add"},
                 {"type": "TranscriptText", "data": "Please add a toggle."}, {"type": "TranscriptEndpoint"},
                 {"type": "TranscriptText", "data": "Thanks."}])
        self.assertEqual(d.text(), "Please add a toggle. Thanks.")
        self.assertIsNone(d.error)

    def test_errors_are_reported(self):
        d = run([{"type": "TranscriptError", "description": "quota exceeded"}])
        self.assertEqual(d.error, "quota exceeded")

    def test_stop_keeps_the_unfinished_phrase(self):
        d = run([{"type": "TranscriptText", "data": "half a sentence"}])
        self.assertEqual(d.stop(0), "half a sentence")

    def test_no_login_gives_a_clear_message(self):
        with mock.patch.object(voice, "CREDENTIALS", os.path.join(os.path.dirname(__file__), "missing.json")):
            with self.assertRaises(ValueError) as e:
                voice.token()
        self.assertIn("signed in", str(e.exception))


if __name__ == "__main__":
    unittest.main()
