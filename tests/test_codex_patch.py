import json, pathlib, subprocess, sys, tempfile, unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import codex_patch, patch


SOURCE = '''const chatGptModels = fn("chatGptModels");
function mapModel(model, nativeModels) {
	return {
		capabilities: nativeModels.find((native) => native.slug === model.slug)?.capabilities ?? null,
		slug: model.slug,
		name: model.display_name,
		isCustom: false
	};
}
'''


class CodexReasoningPatch(unittest.TestCase):
    def test_idempotent(self):
        result = codex_patch.reasoning_controls(SOURCE)
        self.assertEqual(codex_patch.reasoning_controls(result), result)
        self.assertEqual(result.count(codex_patch.MARKER), 1)

    def test_unknown_or_duplicate_mapping_fails_closed(self):
        for source in ('unrecognized version', SOURCE + SOURCE,
                       SOURCE.replace('const chatGptModels', 'const changed'),
                       SOURCE.replace('capabilities: nativeModels.find', 'capabilities: changed.find')):
            with self.subTest(source=source), self.assertRaises(ValueError):
                codex_patch.reasoning_controls(source)

    def test_documented_controls_and_native_metadata_precedence(self):
        script = '''const assert = require("node:assert/strict");
const fn = () => null;
const createModelCapabilities = input => structuredClone(input);
const reasoningEffortLabel = effort => ({low: "Low", medium: "Medium", high: "High", xhigh: "Extra High", max: "Max"})[effort];
''' + codex_patch.reasoning_controls(SOURCE) + '''
const model = {slug: "gpt-6.1-sol", display_name: "GPT-6.1 Sol"};
const mapped = mapModel(model, []);
assert.equal(mapped.slug, model.slug);
assert.equal(mapped.name, model.display_name);
assert.equal(mapped.isCustom, false);
const descriptor = mapped.capabilities.optionDescriptors[0];
assert.equal(descriptor.id, "reasoningEffort");
assert.equal(descriptor.type, "select");
assert.equal(descriptor.currentValue, "medium");
assert.deepEqual(descriptor.options.map(option => option.id), ["low", "medium", "high", "xhigh", "max"]);
assert.deepEqual(descriptor.options.filter(option => option.isDefault).map(option => option.id), ["medium"]);
assert.equal(descriptor.options[3].label, "Extra High");
assert.equal(mapModel({slug: "future-sol"}, []).capabilities, null);
assert.equal(mapModel({slug: "gpt-6-sol"}, []).capabilities, null);
const native = {optionDescriptors: [{id: "reasoningEffort", type: "select", currentValue: "high", options: [{id: "high"}]}]};
assert.strictEqual(mapModel(model, [{slug: model.slug, capabilities: native}]).capabilities, native);
const tier = {id: "serviceTier", type: "select", options: [{id: "default"}]};
const other = {optionDescriptors: [tier]};
Object.freeze(other.optionDescriptors);
Object.freeze(other);
const merged = mapModel(model, [{slug: model.slug, capabilities: other}]).capabilities;
assert.deepEqual(merged.optionDescriptors[0], tier);
assert.equal(merged.optionDescriptors[1].id, "reasoningEffort");
assert.equal(other.optionDescriptors.length, 1);
assert.strictEqual(mapModel({slug: "other"}, [{slug: "other", capabilities: native}]).capabilities, native);
'''
        subprocess.run(['node', '-e', script], check=True, capture_output=True, text=True)

    @unittest.skipUnless(patch.BACKUP.exists(), 'no installed T3 archive')
    def test_installed_overlay_includes_valid_fallback(self):
        overlay = next(iter(patch.server_files().values()))
        self.assertIn(codex_patch.MARKER, overlay)
        self.assertEqual(codex_patch.reasoning_controls(overlay), overlay)
        with tempfile.TemporaryDirectory() as folder:
            target = pathlib.Path(folder) / 'server.mjs'
            target.write_text(overlay, encoding='utf-8')
            subprocess.run(['node', '--check', str(target)], check=True, capture_output=True, text=True)


if __name__ == '__main__':
    unittest.main()
