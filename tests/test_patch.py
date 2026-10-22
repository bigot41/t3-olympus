"""Tests for patch.files() (needs T3's original server.asar backup)."""
import pathlib, sys, unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import patch


@unittest.skipUnless(patch.BACKUP.exists(), "no server.asar backup")
class Files(unittest.TestCase):
    def test_index_html(self):
        html = patch.files()["index.html"]
        hook = html.index("olympus:thread")
        self.assertLess(hook, html.index('<script type="module"'))
        self.assertLess(html.rfind("<script", 0, hook), hook)
        self.assertIn("/olympus.css", html)
        self.assertIn("/olympus.js", html)

    def test_olympus_js(self):
        js = patch.files()["olympus.js"]
        self.assertIn("OlympusTurn", js)


if __name__ == "__main__":
    unittest.main()
