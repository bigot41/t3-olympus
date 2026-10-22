"""Temporary chats: creation, isolation, cleanup. Runs against a fake home folder, never your real data.

    python -m unittest discover tests
"""
import json, os, sqlite3, sys, tempfile, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import temporary  # noqa: E402

TEMP_THREAD, OTHER_THREAD = "t-temp-1", "t-normal-1"
TEMP_SID, OTHER_SID = "s-temp-1", "s-normal-1"


class FakeHome(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        home = self.tmp.name
        self.dir = os.path.join(home, ".t3", "olympus-temporary")
        self.data = os.path.join(home, ".t3", "userdata")
        self.claude = os.path.join(home, ".claude")
        self.db = os.path.join(self.data, "statev2.sqlite")
        self.normal_root = os.path.join(home, "Projects", "site")
        patches = {"HOME": home, "DIR": self.dir, "DATA": self.data, "DB": self.db, "CLAUDE": self.claude}
        for k, v in patches.items():
            p = mock.patch.object(temporary, k, v)
            p.start()
            self.addCleanup(p.stop)
        os.makedirs(os.path.join(self.data, "logs", "provider"))
        os.makedirs(os.path.join(self.data, "attachments", "up-temp"))
        os.makedirs(os.path.join(self.data, "attachments", "up-normal"))
        con = sqlite3.connect(self.db)
        con.executescript("""
            create table projection_projects (project_id, workspace_root, deleted_at);
            create table orchestration_v2_projection_threads (thread_id, project_id, deleted_at);
            create table orchestration_v2_projection_provider_threads (thread_id, payload_json);
            create table orchestration_events (stream_id, payload_json);""")
        con.executemany("insert into projection_projects values (?, ?, null)", [("p-temp", self.dir), ("p-normal", self.normal_root)])
        con.executemany("insert into orchestration_v2_projection_threads values (?, ?, null)",
                        [(TEMP_THREAD, "p-temp"), (OTHER_THREAD, "p-normal")])
        for t, s in ((TEMP_THREAD, TEMP_SID), (OTHER_THREAD, OTHER_SID)):
            con.execute("insert into orchestration_v2_projection_provider_threads values (?, ?)",
                        (t, json.dumps({"nativeThreadRef": {"driver": "claudeAgent", "nativeId": s}})))
        con.execute("insert into orchestration_events values (?, ?)", (TEMP_THREAD, '{"file":"attachments/up-temp/a.png"}'))
        con.execute("insert into orchestration_events values (?, ?)", (OTHER_THREAD, '{"file":"attachments/up-normal/b.png"}'))
        con.commit()
        con.close()
        # what Claude Code and T3 write for both chats
        self.temp_files = self.files(TEMP_THREAD, TEMP_SID, self.dir)
        self.other_files = self.files(OTHER_THREAD, OTHER_SID, self.normal_root)

    def tearDown(self):
        self.tmp.cleanup()

    def files(self, thread, sid, root):
        proj = os.path.join(self.claude, "projects", temporary.slug(root))
        made = [os.path.join(proj, sid + ".jsonl"), os.path.join(self.claude, "file-history", sid, "x"),
                os.path.join(self.claude, "session-env", sid, "y"),
                os.path.join(self.data, "logs", "provider", f"events.{thread}.log")]
        for f in made:
            os.makedirs(os.path.dirname(f), exist_ok=True)
            with open(f, "w") as out:
                out.write("chat text")
        return made

    def gone(self, paths):
        return [p for p in paths if os.path.exists(p)]


class Creation(FakeHome):
    def test_folder_turns_memory_off(self):
        with mock.patch.object(temporary.subprocess, "run"):
            temporary.ensure()
        with open(os.path.join(self.dir, ".claude", "settings.json")) as f:
            self.assertEqual(json.load(f), {"autoMemoryEnabled": False})

    def test_registers_project_only_when_missing(self):
        with mock.patch.object(temporary.subprocess, "run") as run:
            self.assertEqual(temporary.ensure(), "p-temp")
        run.assert_not_called()

    def test_finds_only_temporary_threads(self):
        self.assertEqual(temporary.threads(), [TEMP_THREAD])
        self.assertTrue(temporary.is_temporary(self.dir + os.sep))
        self.assertFalse(temporary.is_temporary(self.normal_root))


class Cleanup(FakeHome):
    def test_purge_removes_this_chat_only(self):
        uploads = temporary.attachments_of(TEMP_THREAD)
        self.assertEqual([os.path.basename(u) for u in uploads], ["up-temp"])
        temporary.purge(TEMP_THREAD, temporary.session_of(TEMP_THREAD), uploads)
        self.assertEqual(self.gone(self.temp_files + uploads), [])
        self.assertEqual(self.gone(self.other_files), self.other_files)
        self.assertTrue(os.path.isdir(os.path.join(self.data, "attachments", "up-normal")))

    def test_purge_rejects_paths(self):
        with self.assertRaises(ValueError):
            temporary.purge("../statev2.sqlite")
        with self.assertRaises(ValueError):
            temporary.purge(TEMP_THREAD, "..\\..\\x")

    def test_sweep_clears_temporary_chats_only(self):
        self.assertEqual(self.gone(self.temp_files), self.temp_files)
        temporary.sweep()
        self.assertEqual(self.gone(self.temp_files), [])
        self.assertEqual(self.gone(self.other_files), self.other_files)


class Isolation(FakeHome):
    def test_sorting_never_moves_temporary_chats(self):
        import organize
        self.assertIsNone(organize.target(self.dir, "anything"))

    def test_helper_only_purges_after_t3_deleted_it(self):
        import helper
        with self.assertRaises(ValueError):
            helper.temporary_leaving({"thread": OTHER_THREAD})  # a saved chat is never cleaned up
        helper.temporary_leaving({"thread": TEMP_THREAD})
        with self.assertRaises(ValueError):
            helper.temporary_purge({"thread": TEMP_THREAD})  # T3 still has it
        con = sqlite3.connect(self.db)
        con.execute("update orchestration_v2_projection_threads set deleted_at = 'now' where thread_id = ?", (TEMP_THREAD,))
        con.commit()
        con.close()
        helper.temporary_purge({"thread": TEMP_THREAD})
        self.assertEqual(self.gone(self.temp_files), [])
        self.assertEqual(self.gone(self.other_files), self.other_files)


class Scrub(FakeHome):
    def test_scrub_removes_deleted_temporary_chats_only(self):
        con = sqlite3.connect(self.db)
        con.execute("create table orchestration_v2_projection_messages (thread_id, payload_json)")
        con.executemany("insert into orchestration_v2_projection_messages values (?, ?)",
                        [(TEMP_THREAD, "secret"), (OTHER_THREAD, "keep")])
        con.commit()
        con.close()
        self.assertEqual(temporary.scrub(), 0)  # still open in T3: left alone
        con = sqlite3.connect(self.db)
        con.execute("update orchestration_v2_projection_threads set deleted_at = 'now'")  # both deleted in T3
        con.commit()
        con.close()
        self.assertEqual(temporary.scrub(), 1)  # only the temporary one is scrubbed
        con = sqlite3.connect(self.db)
        left = {t: [r[0] for r in con.execute(f"select stream_id from orchestration_events where stream_id = ?", (t,))]
                for t in (TEMP_THREAD, OTHER_THREAD)}
        msgs = [r[0] for r in con.execute("select payload_json from orchestration_v2_projection_messages")]
        con.close()
        self.assertEqual(left, {TEMP_THREAD: [], OTHER_THREAD: [OTHER_THREAD]})
        self.assertEqual(msgs, ["keep"])
        with open(self.db, "rb") as f:
            self.assertNotIn(b"secret", f.read())


if __name__ == "__main__":
    unittest.main()
