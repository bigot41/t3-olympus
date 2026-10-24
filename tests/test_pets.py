"""Tests for pets.pyw's drawing: every picture fits its window at every screen scaling."""
import importlib.machinery, importlib.util, pathlib, sys, unittest
from unittest import mock

HERE = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(HERE))
loader = importlib.machinery.SourceFileLoader("pets", str(HERE / "pets.pyw"))
pets = importlib.util.module_from_spec(importlib.util.spec_from_loader("pets", loader))
loader.exec_module(pets)


class Drawing(unittest.TestCase):
    def tearDown(self):
        pets.set_scale(1.0)

    def test_every_scaling_fits(self):
        for scale in (.5, .75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 3.0):
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


class Preferences(unittest.TestCase):
    def test_defaults_preserve_existing_visibility(self):
        with mock.patch.object(pets, "read_json", return_value={}):
            self.assertEqual(pets.pet_settings(), {"selected": None, "size": 100, "sizes": {}})

    def test_empty_selection_stays_empty(self):
        with mock.patch.object(pets, "read_json", return_value={"selected": [], "size": 75, "sizes": {"Dev": 125}}):
            self.assertEqual(pets.pet_settings(), {"selected": [], "size": 75, "sizes": {"Dev": 125}})

    def test_invalid_preferences_are_safe(self):
        for value in (None, [], "bad", {"selected": "all", "size": "bad", "sizes": []}):
            with self.subTest(value=value), mock.patch.object(pets, "read_json", return_value=value):
                self.assertEqual(pets.pet_settings(), {"selected": None, "size": 100, "sizes": {}})
        for value, expected in ((0, 50), (200, 150), (float("nan"), 100), (True, 100)):
            self.assertEqual(pets.valid_size(value), expected)


class Placement(unittest.TestCase):
    def setUp(self):
        pets.set_scale(1)

    def tearDown(self):
        pets.set_scale(1)

    def assert_inside(self, place, area):
        self.assertGreaterEqual(place[0], area[0])
        self.assertGreaterEqual(place[1], area[1])
        self.assertLessEqual(place[0] + pets.W, area[2])
        self.assertLessEqual(place[1] + pets.H, area[3])

    def test_spawn_on_t3_monitor_with_signed_coordinates(self):
        for area in ((1920, 0, 3840, 1040), (-1920, 0, 0, 1040), (0, -1080, 1920, -40)):
            for index in range(12):
                self.assert_inside(pets.place_on_monitor(None, area, index), area)

    def test_old_monitor_positions_are_ignored(self):
        area = (1920, 0, 3840, 1040)
        self.assertEqual(pets.place_on_monitor([500, 700], area, 0), pets.place_on_monitor(None, area, 0))

    def test_saved_positions_are_preserved_and_clamped_after_resize(self):
        area = (-1920, 0, 0, 1040)
        self.assertEqual(pets.place_on_monitor([-1200, 500], area, 0), (-1200, 500))
        self.assert_inside(pets.place_on_monitor([-5, 1030], area, 0), area)

    def test_bad_saved_positions_are_ignored(self):
        area = (0, 0, 1920, 1040)
        for place in ([], [1], "bad", [None, 1], [float("inf"), 1]):
            self.assert_inside(pets.place_on_monitor(place, area, 0), area)

    def test_mixed_sizes_use_nonoverlapping_slots(self):
        area = (0, 0, 1920, 1040)
        pets.set_scale(1.5)
        cell = (pets.W, pets.H)
        large = pets.place_on_monitor(None, area, 0, cell)
        pets.set_scale(.5)
        small = pets.place_on_monitor(None, area, 1, cell)
        self.assertLess(small[0] + pets.W, large[0])

    def test_missing_window_dpi_does_not_compound_custom_size(self):
        pets.set_scale(3)
        with mock.patch.object(pets.user32, "GetDpiForWindow", return_value=0):
            self.assertEqual(pets.dpi_of(None), pets.SYSTEM_SCALE)


class LivePreferences(unittest.TestCase):
    def setUp(self):
        self.app = pets.App.__new__(pets.App)
        self.app.root = mock.Mock()
        self.app.pets = {}
        self.app.places = {}
        self.app.t3_up = True
        self.app.area = (1920, 0, 3840, 1040)
        self.found = [{"name": name, "god": "olympus", "state": "idle", "thread": None, "title": ""}
                      for name in ("Dev", "Work", "Personal")]
        patches = (mock.patch.object(pets, "OFF"), mock.patch.object(pets, "profiles", return_value=self.found),
                   mock.patch.object(pets, "t3_windows", return_value=[123]),
                   mock.patch.object(pets.user32, "GetForegroundWindow", return_value=123),
                   mock.patch.object(pets, "monitor_workarea", return_value=self.app.area),
                   mock.patch.object(pets, "dpi_of", return_value=1.5),
                   mock.patch.object(pets, "pet_settings"), mock.patch.object(pets, "Pet"),
                   mock.patch.object(pets, "write_json"))
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        pets.OFF.exists.return_value = False
        pets.pet_settings.return_value = {"selected": ["Dev"], "size": 75, "sizes": {"Dev": 125}}
        pets.Pet.side_effect = lambda app, info, place, scale: mock.Mock(scale=scale)
        self.addCleanup(pets.set_scale, 1)

    def test_only_selected_pets_spawn_with_size_override_and_dpi(self):
        self.app.poll()
        self.assertEqual(set(self.app.pets), {"Dev"})
        self.assertEqual(pets.Pet.call_args.args[3], 1.875)
        self.assertGreaterEqual(pets.Pet.call_args.args[2][0], 1920)

    def test_clearing_selection_removes_pets_without_exiting(self):
        self.app.poll()
        pet = self.app.pets["Dev"]
        pets.pet_settings.return_value["selected"] = []
        self.app.poll()
        pet.win.destroy.assert_called_once()
        self.assertEqual(self.app.pets, {})
        self.app.root.destroy.assert_not_called()

    def test_monitor_move_recreates_pets_on_new_monitor(self):
        self.app.poll()
        previous = self.app.pets["Dev"]
        previous.win.winfo_x.return_value = 3600
        previous.win.winfo_y.return_value = 800
        pets.monitor_workarea.return_value = (-1920, 0, 0, 1040)
        self.app.poll()
        previous.win.destroy.assert_called_once()
        self.assertLess(pets.Pet.call_args.args[2][0], 0)

    def test_size_change_rebuilds_only_affected_pet(self):
        self.app.poll()
        previous = self.app.pets["Dev"]
        previous.win.winfo_x.return_value = 3600
        previous.win.winfo_y.return_value = 800
        pets.pet_settings.return_value["sizes"]["Dev"] = 50
        self.app.poll()
        previous.win.destroy.assert_called_once()
        self.assertEqual(pets.Pet.call_args.args[3], .75)


if __name__ == "__main__":
    unittest.main()
