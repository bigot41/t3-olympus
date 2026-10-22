# T3 Code hook findings: reacting to `mcp__olympus__wrap_up` without polling

Date: 2026-10-22. Static read of `server.asar.olympus-orig`, extracted to
`C:/Users/moham/re-work/t3-server/` with `npx @electron/asar extract`. The extract errors at the end
because some unpacked native files are missing. That does not matter: `apps/server/dist/client/**`
and `apps/server/dist/*.mjs` came out complete. Nothing below has been tested live yet.

Paths used below:
- C = `t3-server/apps/server/dist/client/assets/`
- S = `t3-server/apps/server/dist/binCli-DF59J6P3.mjs` (server bundle, not minified, has `//#region` source names)

---

## 1. How the client gets thread events

**Transport.** One WebSocket per environment. It carries Effect RPC (`effect/rpc`) with **JSON**
serialization.
- Socket constructor, C`runtime-Dk77ZTQi.js`:
  `zs=Ro(Rs)((e,t)=>{...;return new globalThis.WebSocket(e,t)})`. The runtime layer `Ty=ol(Vi(by,Ev,zs,...))`
  supplies it. It reads `globalThis.WebSocket` **each time it connects**, so a wrapper installed
  before the first connect catches every socket, and one installed late still catches reconnects.
- URL, same file: `function $m(e,t,n){let r=new URL(e.wsBaseUrl);(r.pathname===''||r.pathname==='/')&&(r.pathname='/ws'); ...}`
  So the URL is `ws(s)://<server-origin>/ws?...` (query params carry client metadata/ticket).
- Serialization: `Nl=Ro(jl)(Ml)` with `Ml=jl.of({contentType:'application/json', ... decode:e=>{let t=JSON.parse(typeof e=='string'?e:Al(e));return Array.isArray(t)?t:[t]}, encode:e=>JSON.stringify(...)`.
  A frame can be a string or an ArrayBuffer (UTF-8 JSON), and can hold one message or an array of them.
- The RPC client is not in a Worker. The only `new Worker` calls are Shiki and similar (`worker-DvkHE_S2.js` has no WebSocket).

**Wire messages** (Effect RPC):
- client to server: `{"_tag":"Request","id":"<n>","tag":"orchestration.subscribeThread","payload":{threadId, afterSequence?, requestCompletionMarker?, acceptBoundedSnapshot?, acceptCompactTurnItems?},"headers":[...]}`
- server to client: `{"_tag":"Chunk","requestId":"<n>","values":[ ...stream items ]}`, `{"_tag":"Exit",...}`, `Ping`/`Pong`. The client acks with `{"_tag":"Ack","requestId"}`.
- Unknown `requestId`s are ignored by T3's client (`case 'Chunk': ... i=l.get(n); return !i||... ? W : ...`), so we can safely add our own requests on the same socket.

**Thread stream schema**, C`utils-CxoqT410.js` ~offset 329390 (`JN`), schemas `lve` (input) and `mve` (output):
```
mve = union(
  {kind:'synchronized'},
  {kind:'snapshot', snapshotSequence, projection, historyCursor?, hasMoreHistory?, ...},
  {kind:'event', sequence, event: <fN domain event>},
  {kind:'unknown-event', ...})
```
RPC names (`LN`): `orchestration.subscribeThread`, `orchestration.subscribeShell`, `orchestration.getThreadProjection`,
`orchestration.getTurnItem`, `orchestration.dispatchCommand`, and others.

**Global store?** None. State lives in Effect atoms inside closures. The only `window.*` globals are
Clerk, `desktopBridge`, `__TANSTACK_EVENT_TARGET__` and `__THREE__`. Nothing exposes the thread store.

**Load order.** `index.html` has `<script type="module" crossorigin src="/assets/index-C4f_xMnc.js">` in `<head>`.
patch.py adds `<script src="/olympus.js" defer>` just before `</head>`, so after it. Deferred classic scripts and
non-async module scripts run in document order after parsing. `index-*.js` runs first, but all it does is
`import('./main-DtHZmDQQ.js')`. That import resolves asynchronously, after more fetches, so olympus.js runs
before main or runtime evaluates and before any socket opens. In practice the order is fine. To make it a
guarantee, have patch.py inject a tiny **non-defer** `<script src="/olympus-hook.js"></script>` (or an inline
script) *before* the module tag. It runs synchronously during parsing, ahead of everything T3 loads.

**Caveat: reload.** The client caches thread snapshots in IndexedDB (`t3code:connection-runtime`, v4,
stores `catalog`, `shell`, `thread`, `server-config`, `vcs-refs`, in C`runtime-eUbaXT1l.js`). It then resubscribes with
`afterSequence: <cached snapshotSequence>`. After a reload the server therefore sends only `synchronized` and
newer events, so **the old wrap_up item does not come over the socket again**. Also, with
`acceptCompactTurnItems` the server's snapshot can leave out the locally visible turn items
(S `omitLocalVisibleTurnItems`, line ~308178).

## 2. What a tool call looks like

Turn item union `sN` (C utils). The relevant members:
```
{...base, type:'dynamic_tool', toolName, viewedImagePath?, input:<unknown JSON>, output?, outputOmitted?}
{...base, type:'todo_list', planId, steps:[{id,text,status:'pending'|'running'|'completed',...}], explanation?}
{...base, type:'command_execution', input:string, output?, exitCode?}   // Bash / PowerShell
{...base, type:'file_change' | 'file_search' | 'web_search' | 'subagent' | ...}
base = {id, threadId, runId, nodeId, providerThreadId, providerTurnId, nativeItemRef:{driver,nativeId,strength},
        parentItemId, ordinal, status, title, startedAt, completedAt, updatedAt,
        toolSurface?, toolIcon?, toolSource?, toolNonExecutionKind?}
```
These items reach the client as domain event `{type:'turn-item.updated', id, threadId, runId?, nodeId?, occurredAt, payload:<turn item>}`.

**How the Claude adapter maps tools** (S region `src/orchestration-v2/Adapters/ClaudeAdapterV2.ts`, line 198562+):
- `classifyClaudeNativeTool()` (~199670). Unknown names, which includes every `mcp__*`, become `itemType:'dynamic_tool'`.
- Line ~203248: `for (const toolUse of claudeToolUseBlocksFromAssistantMessage(message)) { ... ensureToolCallStarted({toolName: toolUse.name, toolInput, presentation: mcpToolPresentation$1({toolName}) }) }`
  This is driven by the **complete assistant message** from the SDK. There is no `input_json_delta` handling,
  so the item first appears with the **full input** already in it (status `running`). It is then updated to
  `completed` when the tool_result arrives (same loop, `claudeToolResultEntriesFromMessage`).
- Builder at S ~201084: `{...itemBase, type:'dynamic_tool', toolIcon?, toolSource?, toolName: input.toolName, input: claudeNativeToolInputValue(...), output?}`.
- `mcpToolPresentation$1` (S 174263) parses `^mcp__(.+?)__(.+)$`. For wrap_up it adds `title:'wrap up'` and
  `toolSource:{key:'mcp:olympus', name:'olympus', kind:'integration'}`.
- `nativeItemRef.nativeId` is the Claude `toolu_...` id. Item `id` = `turn-item:provider:claudeAgent:native-item:toolu_...`.

So we expect a live `mcp__olympus__wrap_up` frame like this (inferred from the schemas, not captured):
```json
{"_tag":"Chunk","requestId":"12","values":[{"kind":"event","sequence":123,"event":{
  "type":"turn-item.updated","threadId":"<threadId>...","occurredAt":"...",
  "payload":{"type":"dynamic_tool","toolName":"mcp__olympus__wrap_up","status":"running",
    "input":{"recap":"...","ask":"...","actions":[{"label":"...","message":"..."}]},
    "id":"turn-item:provider:claudeAgent:native-item:toolu_...","nativeItemRef":{"nativeId":"toolu_..."},
    "title":"wrap up","toolSource":{"key":"mcp:olympus","name":"olympus","kind":"integration"}, ...}}}]}
```

**What gets trimmed on the wire** (S region `src/orchestration-v2/WireProjection.ts`, line ~55876):
```js
const MAX_DYNAMIC_VALUE_BYTES = 16384;
case "dynamic_tool": { const { output: rawOutput, ...projected } = item;
  return {...projected, input: summarizeDynamicValue(item.input), output: compactDynamicToolOutput(rawOutput), outputOmitted: ...}; }
```
- `input` passes through **unchanged if its JSON is 16 KB or less**. Otherwise it becomes `{summary, truncated:true}`. A wrap_up input is far below that.
- `output` is cut down to ids and flags. That is fine, since we only need the input.
- This projection covers live events (`projectDomainEventForWire`), WS snapshots, and the HTTP snapshot.
- `orchestration.getTurnItem` returns the detail projection (input up to 256 KB).
- Live `running` tool updates are coalesced over 50 ms (S `ThreadLiveEventCoalescer.ts` ~308044). Harmless.

**After reload, use HTTP.** S line 21558 and 341214:
`GET /api/orchestration/threads/:threadId` returns `{snapshotSequence, projection}`, where projection is
wire-projected and has `turnItems` and `visibleTurnItems[].item`.
Auth is the session cookie (`t3_session_<port>` in desktop mode, S 102533), so a same-origin
`fetch(..., {credentials:'include'})` from page JS should work. The client schema requires header
`x-t3-orchestration-protocol: 2` (C utils `hI=P({authorization:O(j),dpop:O(j),[$D]:A('2')})`).
Untested from page JS, so check it once in DevTools.

## 3. How tool calls show in the DOM (fallback)

C`_chat-CUpeYEZL.js`: rows are `<div data-timeline-row-id={row.id} data-timeline-row-kind={kind} data-message-id data-message-role>`,
with kinds such as `message`, `work`, `work-live` and `turn-fold`. Tool calls are grouped in a virtualized scroller
(`role="region" aria-label="Tool calls" data-tool-group-scroll`, `maintainVisibleContentPosition`).
The label is built from `structuredPayload.toolName/input/title` (`ah(n.toolName,n.input,n.title)`). For an
unknown MCP tool that is just the title ("wrap up"). **The input JSON is not in the DOM**, and rows are
virtualized and collapsed. The DOM is only good for detecting *that* a wrap_up happened. It cannot give us
recap/ask/actions. Poor fallback.

## 4. TodoWrite / task list

The server turns Claude `TodoWrite` (top level only) into a `todo_list` turn item plus a plan projection
(S ~203252 `emitClaudePlanProjection({kind:'todo_list', steps: claudeTodoSteps(input)})`). It is also stored as a
`dynamic_tool` item named `TodoWrite`. The client shows it as a collapsible **"shoulder tab" above the composer**:
`data-composer-shoulder-tab`, `data-composer-tasks-badge`, `data-composer-tasks-list` (`<ul role=list aria-label="Task list. N of M complete.">`),
`data-composer-task-current`, `data-composer-task-progress`, and "Collapse tasks"/"Expand plan" buttons.
Statuses: completed / inProgress / pending. Claude desktop's task panel is the same idea, and T3 already has it.

## 5. Sending a message programmatically

There is no HTTP endpoint for sending (S routes: only auth, connect, projects, and the orchestration
shell/thread snapshot/transcript/history GETs). The client sends with RPC `orchestration.dispatchCommand`
(C`runtime-eUbaXT1l.js`, `EnvironmentCommands`):
```js
X({type:'message.dispatch', commandId:<uuid v4>, createdBy:'user', creationSource:'web', threadId,
   messageId:<uuid>, text, attachments:[], dispatchMode:{type:'start_immediately'} /* or steer_active/queue_after_active */})
// X = e => Vi(Mt.dispatchCommand, e)   (payload is the command itself)
```
With the WebSocket wrapper we hold T3's own socket, so we can `ws.send(JSON.stringify({_tag:'Request', id:'<unique big n>',
tag:'orchestration.dispatchCommand', payload:{...}, headers:<copy shape from an observed T3 Request>}))`.
T3 ignores the reply because the id is unknown. This is cleaner than faking Enter, but it skips T3's composer
logic (choosing steer/queue while a run is active, model selection, title seed). Lower-risk option: keep
the composer method, but click T3's real send button instead of a synthetic keydown, or leave it as it is
(it works).

## 6. Local DB (`~/.t3/userdata/statev2.sqlite`)

- `orchestration_v2_projection_turn_items(turn_item_id, thread_id, run_id, ..., type, status, updated_at, payload_json)`
  holds the full turn item JSON **with the full `input`** (seen for Read, Grep, PowerShell, Skill, ToolSearch).
  `turn_item_id` = `turn-item:provider:claudeAgent:native-item:toolu_...`.
- `orchestration_events(sequence, stream_id, event_type, payload_json, ...)` keeps every `turn-item.updated`
  (8375 rows), with payload = turn item. This includes this session's own tool calls a few seconds old, so writes are near real-time.
- `thread_id` is the T3 UI thread id for main-thread items. Subagent/provider-thread items use a
  `thread:provider:claudeAgent:native-thread:...` id.
- **No `mcp__*` toolName rows exist yet** (0 matches). No MCP tool call has been recorded since this DB started
  (items from 2026-08-15), so MCP items have not been confirmed in storage. The server code gives no reason
  they would be stored differently. A DB query in helper.py
  (`select payload_json from orchestration_v2_projection_turn_items where thread_id=? and type='dynamic_tool' and json_extract(payload_json,'$.toolName') like 'mcp__%wrap_up' order by ordinal desc limit 1`)
  could replace transcript parsing, but it is still polling.

---

## Recommendation

**Wrap `window.WebSocket` from a tiny script that runs before T3's bundle**, and parse the Effect RPC JSON frames:

```js
// olympus-hook.js : injected by patch.py as a plain <script> BEFORE T3's <script type="module">
(() => {
  const Native = window.WebSocket, dec = new TextDecoder();
  const subs = new Map();                       // requestId -> threadId for orchestration.subscribeThread
  const emit = (item, threadId) => window.dispatchEvent(new CustomEvent("olympus:turn-item", { detail: { item, threadId } }));
  const parse = (d) => { try { const v = JSON.parse(typeof d === "string" ? d : dec.decode(d)); return Array.isArray(v) ? v : [v]; } catch { return []; } };
  class Hooked extends Native {
    constructor(url, p) {
      super(url, p);
      if (!new URL(url, location.href).pathname.endsWith("/ws")) return;
      window.__olympusSocket = this;
      const send = this.send.bind(this);
      this.send = (d) => { for (const m of parse(d)) if (m._tag === "Request" && m.tag === "orchestration.subscribeThread") subs.set(String(m.id), m.payload.threadId); return send(d); };
      this.addEventListener("message", (e) => {
        for (const m of parse(e.data)) {
          if (m._tag !== "Chunk" || !subs.has(String(m.requestId))) continue;
          for (const v of m.values || []) {
            if (v.kind === "event" && v.event?.type === "turn-item.updated") emit(v.event.payload, subs.get(String(m.requestId)));
            if (v.kind === "snapshot") for (const it of v.projection?.turnItems || []) emit(it, subs.get(String(m.requestId)));
          }
        }
      });
    }
  }
  window.WebSocket = Hooked;
})();
```
nextstep.js then listens for `olympus:turn-item` where `item.type==='dynamic_tool' && item.toolName.endsWith('__wrap_up')`,
draws the card from `item.input`, and clears it on a later `user_message` item for the same thread.
**On page load or thread switch**, fill the gap left by the IndexedDB cache with one
`fetch('/api/orchestration/threads/'+id, {credentials:'include', headers:{'x-t3-orchestration-protocol':'2'}})`
and take the last wrap_up in `projection.turnItems` that has no later `user_message`. If that fetch turns out
not to work, call helper.py's `/wrapup` once instead. That removes the 2 s polling completely.

Things to check live:
1. The socket path really ends in `/ws` (log `url` once).
2. The `Request` header shape (only matters for sending).
3. The HTTP snapshot works with cookie auth from page JS.
4. One real wrap_up frame looks like section 2.
