"""new_profile.make_profile, against a temp folder with T3 and Claude Code stubbed out.

    python -m unittest discover -s tests
"""
import json, os, pathlib, sys, tempfile, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import new_profile  # noqa: E402  (importing must not make a profile)


class MakeProfile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.added, self.registered = [], []
        for name, value in {"PROFILES": str(root / "profiles"), "GODS": root / "gods.json", "HOME": root / "home",
                            "t3_add": lambda title, folder: self.added.append((title, folder)) or True,
                            "register": lambda folder: self.registered.append(folder)}.items():
            p = mock.patch.object(new_profile, name, value)
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_makes_folder_claude_md_and_project(self):
        r = new_profile.make_profile("gamedev", "athena", "Unity games and level design")
        folder = pathlib.Path(r["folder"])
        text = (folder / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertEqual(r["title"], "Gamedev")
        self.assertTrue(text.startswith("# Gamedev profile"))
        self.assertIn("Unity games and level design", text)
        self.assertTrue(r["added"])
        self.assertEqual(self.added, [("Gamedev", folder)])
        self.assertEqual(self.registered, [folder])
        self.assertEqual(json.loads(new_profile.GODS.read_text(encoding="utf-8")), {"Gamedev": "athena"})

    def test_keeps_an_existing_claude_md_without_about(self):
        folder = pathlib.Path(new_profile.PROFILES) / "notes"
        folder.mkdir(parents=True)
        (folder / "CLAUDE.md").write_text("mine", encoding="utf-8")
        new_profile.make_profile("notes", None)
        self.assertEqual((folder / "CLAUDE.md").read_text(encoding="utf-8"), "mine")
        self.assertFalse(new_profile.GODS.exists())

    def test_agent_file(self):
        new_profile.make_profile("dev", None, agent=True)
        agent = new_profile.HOME / ".claude" / "agents" / "dev.md"
        self.assertIn("name: dev", agent.read_text(encoding="utf-8"))

    def test_bad_name_and_unknown_god(self):
        for name in ("", "has space", "../up", "a/b"):
            with self.assertRaises(ValueError):
                new_profile.make_profile(name, None)
        with self.assertRaises(ValueError):
            new_profile.make_profile("ok", "zeus")
        self.assertEqual(self.added, [])


if __name__ == "__main__":
    unittest.main()
