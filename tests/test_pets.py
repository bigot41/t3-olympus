"""Tests for pets.pyw's drawing: every picture fits its window at every screen scaling."""
import importlib.machinery, importlib.util, pathlib, sys, unittest

HERE = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(HERE))
loader = importlib.machinery.SourceFileLoader("pets", str(HERE / "pets.pyw"))
pets = importlib.util.module_from_spec(importlib.util.spec_from_loader("pets", loader))
loader.exec_module(pets)


class Drawing(unittest.TestCase):
    def tearDown(self):
        pets.set_scale(1.0)

    def test_every_scaling_fits(self):
        for scale in (1.0, 1.25, 1.5, 1.75, 2.0):
            with self.subTest(scale=scale):
                pets.set_scale(scale)
                coin = pets.coin_image("olympus")
                self.assertLessEqual(coin.width, pets.SPRITE_W)
                for state in ("working", "done", "needs"):
                    frame = pets._with_badge(coin, state, 0.3)
                    self.assertEqual(frame.size, (pets.SPRITE_W, pets.SPRITE_H))
                    # the badge sits wholly inside the frame: nothing clipped at its top or right
                    box = frame.getchannel("A").getbbox()
                    self.assertGreater(box[1], 0, state)
                    self.assertLess(box[2], pets.SPRITE_W, state)

    def test_sun_centre_stays_still(self):
        pets.set_scale(2.0)
        a, b = pets.badge("done", 0.0), pets.badge("done", 0.4)
        c = a.width // 2
        centre = (c - 3, c - 3, c + 3, c + 3)
        self.assertEqual(a.crop(centre).tobytes(), b.crop(centre).tobytes())

    def test_plaque_fits(self):
        for scale in (1.0, 1.5, 2.0):
            pets.set_scale(scale)
            plaque = pets.label_image("Projects", "#7a4ea0", "#ffffff")
            self.assertLessEqual(plaque.width, pets.W)

    def test_premultiplied(self):
        from PIL import Image
        img = Image.new("RGBA", (1, 1), (200, 100, 50, 128))
        self.assertEqual(pets.premultiplied(img), bytes((50 * 128 // 255, 100 * 128 // 255, 200 * 128 // 255, 128)))


class State(unittest.TestCase):
    def test_reads_profiles(self):
        if not pets.DB.exists():
            self.skipTest("no T3 database")
        for p in pets.profiles():
            self.assertIn(p["state"], ("idle", "working", "done", "needs"))


if __name__ == "__main__":
    unittest.main()
