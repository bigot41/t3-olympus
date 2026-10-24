"""picture.locate and a DXF drawn to SVG. No T3 or network needed."""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ezdxf
import picture  # noqa: E402


class Locate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        open(os.path.join(self.root, "room.png"), "wb").close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_picture_inside_the_project(self):
        kind, path = picture.locate(self.root, "room.png")
        self.assertEqual(kind, "image")
        self.assertEqual(os.path.basename(path), "room.png")

    def test_project_name_on_the_front_is_ignored(self):
        kind, path = picture.locate(self.root, os.path.basename(self.root) + "/room.png")
        self.assertEqual(kind, "image")
        self.assertTrue(path.endswith("room.png"))

    def test_parent_path_is_refused(self):
        with self.assertRaises(ValueError):
            picture.locate(self.root, "../room.png")

    def test_absolute_path_inside_the_project(self):
        kind, path = picture.locate(self.root, self.root.replace("\\", "/") + "/room.png")
        self.assertEqual(kind, "image")
        self.assertTrue(path.endswith("room.png"))

    def test_other_files_are_refused(self):
        open(os.path.join(self.root, "notes.txt"), "w").close()
        with self.assertRaises(ValueError):
            picture.locate(self.root, "notes.txt")


class Drawing(unittest.TestCase):
    def test_a_line_becomes_svg(self):
        doc = ezdxf.new()
        doc.modelspace().add_line((0, 0), (10, 0))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "line.dxf")
            doc.saveas(path)
            out = picture.dxf_svg(path)
        self.assertIn("<path", out)
        self.assertNotIn("<?xml", out)

    def test_page_embeds_the_drawing(self):
        page = picture.html("tok", "drawing", "<svg></svg>")
        self.assertIn("<svg></svg>", page)
        self.assertNotIn("/file", page)
