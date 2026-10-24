"""Name ordinary chats with Claude's small title command, not the coding prompt."""
import json, pathlib, sys

MARKER = '"olympus-title-small-v1"'
SQLITE_MARKER = '"olympus-sqlite-sidecar-v1"'
AGENTS_MARKER = '"olympus-background-agents-v1"'
REQUEST_ENV = {"CLAUDE_CODE_DISABLE_THINKING": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
               "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1"}


def lean_titles(source):
    if MARKER in source:
        return source
    if '"olympus-lean-title-v1"' in source:
        raise ValueError("Rebuild the title overlay from the original server backup")
    start = source.find('return fromRunner("ClaudeTextGeneration",')
    end = source.find('//#endregion', start)
    if start < 0 or end < 0:
        raise ValueError("Unsupported T3 version: Claude text-generation runner not found")
    block = source[start:end]
    python = str(pathlib.Path(sys.executable).with_name("python.exe")) if sys.executable.lower().endswith("pythonw.exe") else sys.executable
    script = str(pathlib.Path(__file__).with_name("title_request.py"))
    replacements = {
        'modelSelection, investigate }) {':
            'modelSelection, investigate, titleMessage }) {\n\t\tconst ordinaryTitle = operation === "generateThreadTitle" && !investigate;',
        'resolveSpawnCommand(claudeSettings.binaryPath || "claude", [':
            'resolveSpawnCommand(ordinaryTitle ? ' + json.dumps(python) + ' : claudeSettings.binaryPath || "claude", ordinaryTitle ? ['
            + json.dumps(script) + ', "--cli", claudeSettings.binaryPath || "claude", "--model", '
            'resolveClaudeCatalogApiModelId(catalog, resolvedModelSelection)] : [',
        'stdin: { stream: encodeText$1(make$267(prompt)) },':
            'stdin: { stream: encodeText$1(make$267(ordinaryTitle ? String(titleMessage ?? "").slice(0, 2000) : prompt)) },',
        'const output = yield* decodeClaudeOutput(rawStdout)':
            'if (ordinaryTitle) return yield* decodeJsonReply({ operation, outputSchema: outputSchemaJson }, "Claude", rawStdout);\n\t\tconst output = yield* decodeClaudeOutput(rawStdout)'
    }
    for original, replacement in replacements.items():
        if block.count(original) != 1:
            raise ValueError("Unsupported T3 version: title patch anchor changed")
        block = block.replace(original, replacement, 1)
    source = source[:start] + MARKER + ';\n' + block + source[end:]
    anchor = 'operation: "generateThreadTitle",\n\t\t\t\tcwd: input.cwd,'
    if source.count(anchor) != 1:
        raise ValueError("Unsupported T3 version: title message anchor changed")
    return source.replace(anchor, anchor + '\n\t\t\t\ttitleMessage: input.message,', 1)


def sqlite_sidecars(source):
    """Let a Codex status check replace stray sqlite scratch files with shortcuts.

    Codex writes -shm/-wal files beside the shadow-home database shortcut. The real
    Codex folder has the same names. T3 used to stop the whole provider check there.
    """
    if SQLITE_MARKER in source:
        return source
    needle = 'if (!REPLACEABLE_SHARED_RUNTIME_ENTRIES.has(input.entryName)) return yield* new CodexShadowHomeEntryConflictError({'
    anchor = 'function resolveHomePath(path, home, value) {'
    if source.count(needle) != 1 or source.count(anchor) != 1:
        raise ValueError("Unsupported T3 version: Codex shadow home conflict check changed")
    helper = (
        'function isReplaceableSqliteSidecar(entryName) {\n'
        '\treturn entryName.endsWith(".sqlite-shm") || entryName.endsWith(".sqlite-wal");\n'
        '}\n'
    )
    source = source.replace(anchor, SQLITE_MARKER + ';\n' + helper + anchor, 1)
    replacement = (
        'if (!REPLACEABLE_SHARED_RUNTIME_ENTRIES.has(input.entryName) && '
        '!isReplaceableSqliteSidecar(input.entryName)) return yield* new CodexShadowHomeEntryConflictError({'
    )
    return source.replace(needle, replacement, 1)


def background_agents(source):
    if AGENTS_MARKER in source:
        return source
    replacements = {
        'const OrchestratorMcpDelegateTaskResult = Struct({':
            AGENTS_MARKER + ';\nconst OrchestratorMcpDelegateTaskResult = Struct({\n'
            '\tbackgrounded: optional$9(Boolean$5),\n'
            '\tbackgroundNotice: optional$9(String$7),',
        'return result.hasPendingQuestion || result.pendingApproval !== null || isTerminalTaskStatus(result.status);':
            'return result.backgrounded === true || result.hasPendingQuestion || result.pendingApproval !== null || isTerminalTaskStatus(result.status);',
        '\t\t\ttaskId: task.id,\n\t\t\tchildThreadId: task.childThreadId,\n\t\t\tchildRunId: childRun?.id ?? null,':
            '\t\t\tbackgrounded: task.completionWake === "always" && !isTerminalTaskStatus(status),\n'
            '\t\t\ttaskId: task.id,\n\t\t\tchildThreadId: task.childThreadId,\n\t\t\tchildRunId: childRun?.id ?? null,',
        'if (isSome(waited) && isTerminalTaskStatus(waited.value.status)) return waited.value;':
            'if (isSome(waited) && waited.value.backgrounded === true) return { ...waited.value,\n'
            '\t\t\t\tbackgroundNotice: "The user sent this child task to the background. It continues running and will notify this thread on completion. '
            'Return control to the user by ending this parent reply now. Do not wait, poll, stop the child, or start a replacement task."\n'
            '\t\t\t};\n'
            '\t\t\tif (isSome(waited) && isTerminalTaskStatus(waited.value.status)) return waited.value;'
    }
    for original, replacement in replacements.items():
        if source.count(original) != 1:
            raise ValueError("Unsupported T3 version: background-agent wait anchor changed")
        source = source.replace(original, replacement, 1)
    return source
