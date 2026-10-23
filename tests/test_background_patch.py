import pathlib, sys, unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import background_patch, patch

SOURCE = '''
before();
return fromRunner("ClaudeTextGeneration", fn("runClaudeJson")(function* ({ operation, modelSelection, investigate }) {
const settings = {
...typeof thinking === "boolean" ? { alwaysThinkingEnabled: thinking } : {},
};
const command = resolveSpawnCommand(claudeSettings.binaryPath || "claude", [
"--json-schema",
				jsonSchemaStr,
...cliEffort ? ["--effort", cliEffort] : [],
"--settings",
				settingsJson,
]);
const input = { stdin: { stream: encodeText$1(make$267(prompt)) }, };
const spawn = { env: claudeEnvironment };
const child = { env: claudeEnvironment };
const output = yield* decodeClaudeOutput(rawStdout);
return yield* decodeEffect(outputSchemaJson)(envelope?.structured_output);
}));
//#endregion
operation: "generateThreadTitle",
				cwd: input.cwd,
after();
'''


class BackgroundPatch(unittest.TestCase):
    def test_ordinary_titles_use_small_command(self):
        result = background_patch.lean_titles(SOURCE)
        self.assertIn('operation === "generateThreadTitle" && !investigate', result)
        self.assertIn('title_request.py', result)
        self.assertIn('"--cli", claudeSettings.binaryPath || "claude", "--model"', result)
        self.assertIn('titleMessage: input.message,', result)
        self.assertIn('String(titleMessage ?? "").slice(0, 2000) : prompt', result)
        self.assertIn('if (ordinaryTitle) return yield* decodeJsonReply', result)
        self.assertNotIn('const localTitle', result)
        self.assertIn('...typeof thinking === "boolean" ? { alwaysThinkingEnabled: thinking }', result)
        self.assertIn('"--json-schema",\n\t\t\t\tjsonSchemaStr,', result)
        self.assertEqual(result.count('env: claudeEnvironment'), 2)
        self.assertTrue(result.startswith("\nbefore();"))
        self.assertTrue(result.endswith("after();\n"))

    def test_idempotent(self):
        result = background_patch.lean_titles(SOURCE)
        self.assertEqual(background_patch.lean_titles(result), result)

    def test_sqlite_sidecars_are_replaceable(self):
        source = (
            'const REPLACEABLE_SHARED_RUNTIME_ENTRIES = /* @__PURE__ */ new Set(["mcp-oauth-locks"]);\n'
            'function resolveHomePath(path, home, value) {}\n'
            'if (!REPLACEABLE_SHARED_RUNTIME_ENTRIES.has(input.entryName)) '
            'return yield* new CodexShadowHomeEntryConflictError({\n'
        )
        result = background_patch.sqlite_sidecars(source)
        self.assertIn('entryName.endsWith(".sqlite-shm") || entryName.endsWith(".sqlite-wal")', result)
        self.assertIn('!isReplaceableSqliteSidecar(input.entryName)', result)
        self.assertEqual(result.count('CodexShadowHomeEntryConflictError'), 1)
        self.assertEqual(background_patch.sqlite_sidecars(result), result)
        with self.assertRaises(ValueError):
            background_patch.sqlite_sidecars('no shadow home here')

    def test_unknown_source_fails_closed(self):
        with self.assertRaises(ValueError):
            background_patch.lean_titles("new T3 implementation")
        with self.assertRaises(ValueError):
            background_patch.lean_titles(SOURCE.replace('modelSelection, investigate }) {', 'changed header'))
        with self.assertRaises(ValueError):
            background_patch.lean_titles(SOURCE.replace('cwd: input.cwd,', 'cwd: changed,'))
        with self.assertRaises(ValueError):
            background_patch.lean_titles('"olympus-lean-title-v1";' + SOURCE)

    @unittest.skipUnless(patch.BACKUP.exists(), "no installed T3 archive")
    def test_installed_version_has_one_checked_overlay(self):
        overlays = patch.server_files()
        self.assertEqual(len(overlays), 1)
        overlay = next(iter(overlays.values()))
        self.assertIn(background_patch.MARKER, overlay)
        self.assertIn("title_request.py", overlay)
        self.assertNotIn("olympus-title-local-v1", overlay)
        self.assertIn(background_patch.SQLITE_MARKER, overlay)
        self.assertIn('!isReplaceableSqliteSidecar(input.entryName)', overlay)
        self.assertEqual(background_patch.sqlite_sidecars(overlay), overlay)


if __name__ == "__main__":
    unittest.main()
