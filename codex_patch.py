"""Restore documented effort controls when ChatGPT lists a model before Codex."""

MARKER = '"olympus-codex-effort-v1"'


def reasoning_controls(source):
    if MARKER in source:
        return source
    anchor = 'const chatGptModels = fn("chatGptModels")'
    original = 'capabilities: nativeModels.find((native) => native.slug === model.slug)?.capabilities ?? null,'
    if source.count(anchor) != 1 or source.count(original) != 1:
        raise ValueError("Unsupported T3 version: ChatGPT model capabilities mapping changed")
    helper = '''function olympusCodexModelCapabilities(slug, capabilities) {
	if (slug !== "gpt-6.1-sol" || capabilities?.optionDescriptors?.some((option) => option.id === "reasoningEffort")) return capabilities;
	return createModelCapabilities({ optionDescriptors: [
		...(capabilities?.optionDescriptors ?? []),
		{
			id: "reasoningEffort",
			label: "Reasoning",
			type: "select",
			currentValue: "medium",
			options: ["low", "medium", "high", "xhigh", "max"].map((effort) => ({
				id: effort,
				label: reasoningEffortLabel(effort),
				...(effort === "medium" ? { isDefault: true } : {})
			}))
		}
	] });
}
'''
    replacement = 'capabilities: olympusCodexModelCapabilities(model.slug, nativeModels.find((native) => native.slug === model.slug)?.capabilities ?? null),'
    return source.replace(anchor, MARKER + ';\n' + helper + anchor, 1).replace(original, replacement, 1)
