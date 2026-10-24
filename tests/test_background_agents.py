import json, pathlib, re, sqlite3, subprocess, sys, tempfile, unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import background_patch, helper, patch


SOURCE = '''const OrchestratorMcpDelegateTaskResult = Struct({});
function endsTaskWait(result) {
return result.hasPendingQuestion || result.pendingApproval !== null || isTerminalTaskStatus(result.status);
}
const response = {
\t\t\ttaskId: task.id,
\t\t\tchildThreadId: task.childThreadId,
\t\t\tchildRunId: childRun?.id ?? null,
};
if (isSome(waited) && isTerminalTaskStatus(waited.value.status)) return waited.value;
'''


class ServerPatch(unittest.TestCase):
    def test_idempotent_and_does_not_interrupt_work(self):
        result = background_patch.background_agents(SOURCE)
        self.assertEqual(background_patch.background_agents(result), result)
        self.assertIn('result.backgrounded === true', result)
        self.assertIn('backgrounded: task.completionWake === "always" && !isTerminalTaskStatus(status)', result)
        self.assertIn('backgroundNotice:', result)
        self.assertNotIn('run.interrupt', result)
        self.assertNotIn('thread.stop', result)
        self.assertNotIn('completion-delivery.dispose', result)

    def test_changed_or_duplicate_anchors_fail_closed(self):
        for anchor in ('const OrchestratorMcpDelegateTaskResult = Struct({',
                       'return result.hasPendingQuestion', 'taskId: task.id,',
                       'if (isSome(waited) && isTerminalTaskStatus(waited.value.status)) return waited.value;'):
            with self.subTest(anchor=anchor), self.assertRaises(ValueError):
                background_patch.background_agents(SOURCE.replace(anchor, 'changed'))
        with self.assertRaises(ValueError):
            background_patch.background_agents(SOURCE + SOURCE)

    def test_release_predicate_and_tool_reply_keep_child_running(self):
        result = background_patch.background_agents(SOURCE)
        predicate = re.search(r'function endsTaskWait\(result\) \{.*?\n\}', result, re.S).group()
        branch = result[result.index('if (isSome(waited)'):]
        script = '''const assert = require("node:assert/strict");
const isTerminalTaskStatus = status => ["completed", "failed", "cancelled", "interrupted"].includes(status);
''' + predicate + '''
const active = { status: "running", hasPendingQuestion: false, pendingApproval: null, backgrounded: false };
assert.equal(endsTaskWait(active), false);
assert.equal(endsTaskWait({ ...active, backgrounded: true }), true);
assert.equal(endsTaskWait({ ...active, hasPendingQuestion: true }), true);
assert.equal(endsTaskWait({ ...active, pendingApproval: {} }), true);
assert.equal(endsTaskWait({ ...active, status: "completed" }), true);
const reply = new Function("waited", "isSome", "isTerminalTaskStatus", ''' + json.dumps(branch) + ''');
const backgrounded = reply({ value: { ...active, taskId: "same-task", backgrounded: true } }, () => true, isTerminalTaskStatus);
assert.equal(backgrounded.status, "running");
assert.equal(backgrounded.taskId, "same-task");
assert.match(backgrounded.backgroundNotice, /ending this parent reply now/);
'''
        subprocess.run(['node', '-e', script], check=True, capture_output=True, text=True)

    @unittest.skipUnless(patch.BACKUP.exists(), 'no installed T3 archive')
    def test_installed_overlay_is_valid_and_wait_listens_for_policy_updates(self):
        overlay = next(iter(patch.server_files().values()))
        self.assertIn(background_patch.AGENTS_MARKER, overlay)
        self.assertIn('thread: "parent",\n\t\teventType: "subagent.updated"', overlay)
        self.assertIn('mapEffect$2(() => readTask(scope, taskId, false, true)), filter$3(endsTaskWait)', overlay)
        with tempfile.TemporaryDirectory() as folder:
            target = pathlib.Path(folder) / 'server.mjs'
            target.write_text(overlay, encoding='utf-8')
            subprocess.run(['node', '--check', str(target)], check=True, capture_output=True, text=True)


class WaitingAgents(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = pathlib.Path(self.temp.name) / 'state.sqlite'
        con = sqlite3.connect(self.db)
        con.executescript('''
            create table orchestration_v2_projection_runs (run_id text, thread_id text, status text);
            create table orchestration_v2_projection_subagents (
                thread_id text, run_id text, origin text, status text, payload_json text);
            insert into orchestration_v2_projection_runs values ('run', 'parent', 'running');
            insert into orchestration_v2_projection_runs values ('old', 'parent', 'completed');
            insert into orchestration_v2_projection_runs values ('run-other', 'other', 'running');
        ''')
        con.close()
        patched = mock.patch.object(helper, 'DB', str(self.db))
        patched.start()
        self.addCleanup(patched.stop)

    def add_task(self, name, thread='parent', run='run', origin='app_owned', status='running', **extra):
        payload = {'id': name, 'childThreadId': 'child', 'completionWake': 'settled_only', **extra}
        con = sqlite3.connect(self.db)
        con.execute('insert into orchestration_v2_projection_subagents values (?, ?, ?, ?, ?)',
                    (thread, run, origin, status, json.dumps(payload)))
        con.commit()
        con.close()

    def test_only_live_waiting_delegations_of_this_parent_are_listed(self):
        self.add_task('wanted')
        self.add_task('already-background', completionWake='always')
        self.add_task('native', origin='provider_native')
        self.add_task('finished', status='completed')
        self.add_task('old-run', run='old')
        self.add_task('other-thread', thread='other', run='run-other')
        self.add_task('disposed', completionDelivery={'state': 'disposed'})
        self.add_task('no-child', childThreadId=None)
        self.assertEqual(helper.waiting_agents('parent'), {'tasks': [{'id': 'wanted'}]})

    def test_empty_and_unrelated_threads_have_no_button(self):
        self.assertEqual(helper.waiting_agents('missing'), {'tasks': []})
        self.assertEqual(helper.waiting_agents("' or 1=1 --"), {'tasks': []})

    def test_pending_and_waiting_tasks_remain_eligible(self):
        self.add_task('pending', status='pending', completionDelivery=None)
        self.add_task('waiting', status='waiting')
        self.assertEqual(helper.waiting_agents('parent'), {'tasks': [{'id': 'pending'}, {'id': 'waiting'}]})


if __name__ == '__main__':
    unittest.main()
