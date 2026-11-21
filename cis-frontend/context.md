# context.md — Frontend handoff for the backend session

Audience: the Claude session building the FastAPI backend for **Conversational Intelligence Studio** (CIS). `project_context.md` stays the source of truth for the API contract; this file explains exactly how the finished frontend uses it, so nothing has to be guessed.

**Status (after the verification pass):** the frontend builds (`npm run build`, Vite 5, React 18) and was driven in headless Chromium (welcome screen at 1280, 1024, 768 and 390 px; workspace at 1280 and 390 px) against a **local stub** that mimics the contract in `project_context.md` (including a history endpoint that returns only partial metadata). It has **not** been tested against the real FastAPI backend, which is the main remaining risk: treat the contract details below as "implemented to spec and verified against a stub", not "verified end to end". Fonts (DM Serif Display / DM Sans) come from Google Fonts and could not be loaded in the test sandbox, so the serif headings were only seen in a fallback serif.

## 1. Product in one paragraph

A studio for talking to three specialised professional AI analysts about pasted conversation text (no uploads, no auth). Analysts are **three system-prompt presets for one backend and one `/chat` endpoint**. There is no per-analyst backend logic.

| id | Name | Focus |
|---|---|---|
| `customer` | Customer Intelligence | Customer–business conversations: intent, recurring complaints, unresolved follow-ups, friction |
| `workplace` | Workplace Intelligence | Internal team conversations: blockers, breakdowns, items flagged for **human review** (never findings of misconduct) |
| `patterns` | Communication Patterns | Group and per-participant observable roles, repeated follow-ups, unanswered questions, handoffs |

All three presets share the same safeguards (observable behaviour only, no scores or rankings, no invented quotes, no protected-attribute inference, ask for more material if thin, anonymise reminder). Full text is in `src/data/analysts.js`. The backend must treat `system_prompt` as opaque text.

## 2. Frontend structure

```
package.json            scripts: dev, build, preview (port 3000)
index.html              loads DM Serif Display + DM Sans from Google Fonts
vite.config.js
.env.example            VITE_API_BASE_URL
src/main.jsx            entry
src/App.jsx             ALL application state + wiring (no state library)
src/styles.css          design tokens (Quiet Intelligence) + all styles
src/services/api.js     the only code that calls the backend
src/data/analysts.js    3 presets: name, copy, starters, system_prompt
src/components/Welcome.jsx   Screen A: analyst selection
src/components/Sidebar.jsx   new chat, analyst mode, recent sessions, /health status
src/components/Chat.jsx      thread, markdown rendering, metadata, composer, system-prompt input
```

### State (in `App.jsx`)
`view` (`welcome|workspace`), `analystId`, `sessionId`, `systemPrompt`, `messages`, `sessions` (local index), `loading`, `loadingHistory`, `error`, `health`.

## 3. Environment variables

| Name | Where | Meaning |
|---|---|---|
| `VITE_API_BASE_URL` | frontend, **build time** | Backend base URL, no trailing slash. In `npm run dev` it falls back to `http://localhost:8000` if unset. In a production build there is **no fallback** (requests would go to the page's own origin), so it must be set. |

Docker note: because Vite inlines the variable at build time, pass it as a build arg (`ARG VITE_API_BASE_URL` then `ENV VITE_API_BASE_URL=$VITE_API_BASE_URL` before `npm run build`) in the frontend Dockerfile. For `make up`, the browser calls the backend from the user's machine, so it must be `http://localhost:8000`.

## 4. API contract as the frontend uses it

Base: `${VITE_API_BASE_URL}`. All bodies are JSON. Field names are exactly those in `project_context.md`.

### `GET /health`
Called once when the workspace opens. Only success/failure is used (drives the "Backend connected / unreachable" indicator). Response shape per spec: `{"status":"ok","keys_configured":2,"cache_enabled":true}`.

### `POST /chat`
Request body:
```json
{ "session_id": "s-<uuid>", "message": "latest message only", "system_prompt": "..." }
```
- `session_id`: generated in the browser as `s-` + `crypto.randomUUID()` (38 chars, within the 1–128 limit). A new one is generated on first load and on every "New conversation" or analyst switch from a non-empty session.
- `message`: the **trimmed** text; the composer blocks sending when empty or over 4000 characters, so a 422 should be rare.
- `system_prompt`: sent on **every** request (the currently selected preset text, or the user's edit). It is omitted from the body only when empty/whitespace.
- The frontend never sends history. Backend owns it.

Response used:
```json
{ "session_id": "...", "reply": "...", "metadata": {
  "resolution_source": "LIVE_INFERENCE | LLM_CACHE", "model": "...", "latency_ms": 812,
  "input_tokens": 42, "output_tokens": 120, "key_id": "key_1 | null", "fallback_attempts": 0 } }
```
The frontend stores `reply` as the assistant message and `metadata` verbatim on that message.

### `GET /sessions/{session_id}/messages`
Used when the user reopens a session from "Recent sessions". The ID is URL-encoded. Expected shape: `{"session_id": "...", "messages": [{"role":"user|assistant","content":"...","metadata":{...}?}]}`, oldest first.
- **Unknown session:** the frontend treats a 404 as an error and shows the generic server message. Preferred backend behaviour: either 404, or `200` with `"messages": []`. Either works.
- **Partial metadata:** the spec's history example returns only `resolution_source`, `input_tokens`, `output_tokens`. The UI renders any missing field (`model`, `latency_ms`, `key_id`, `fallback_attempts`) as **"Not stored"** and shows a note under "More" that the response was reloaded from history. It never invents values. **Requirement for the backend:** persist and return all seven metadata fields per assistant message in history (`key_id` may be `null`, and must be present as `null` on cache hits). The frontend needs no change when you do: present fields simply replace "Not stored".
- **Unknown session:** a `404` from this endpoint shows "This session could not be found on the server, so its messages can't be reloaded." (Verified with a stale local index entry.)

## 5. Session lifecycle

1. Session IDs are created client-side; the backend creates the session implicitly on the first `POST /chat` with an unseen ID.
2. The backend has no "list sessions" endpoint and the frontend does not expect one. The sidebar's "Recent sessions" is a **local index in `localStorage`** (key `cis.sessions.v1`: id, title = first 48 chars of the first message, analystId, systemPrompt, updatedAt; max 30). It is written only after a successful `/chat`.
3. Reopening a session: sets the session ID, restores that session's analyst and system prompt from the local index, and calls `GET /sessions/{id}/messages` for the content. If the browser's localStorage is cleared, old sessions vanish from the list but remain in the database.
4. Switching analyst: on an empty session it just swaps the preset; on a session with messages it starts a new session, so one session never mixes analysts.

## 6. How system prompts are passed

- Selecting an analyst loads its preset into `systemPrompt`. The "Instructions" panel exposes it in a textarea (`data-testid="system-prompt-input"`) where the user may edit it; "Reset to preset" restores it.
- **Assumption for the backend:** the `system_prompt` received with a request is the instruction set for that turn. The frontend may send an edited prompt mid-session. Suggested handling: use the value from the current request when present, otherwise fall back to the one stored for the session; store the latest used value. **Open decision for you:** first-wins vs latest-wins. The UI text currently says "Changes apply to your next message in this session", which assumes **latest-wins**. If you choose first-wins, tell the frontend session so the copy can change.
- Cache note: identical first messages in new sessions must hit the cache per the assignment. The preset prompt is identical across such sessions, so including `system_prompt` in the cache key still works, but different analysts (different prompts) will correctly miss each other's cache entries.

## 7. How metadata is displayed

Each assistant message carries a **compact, always-visible metadata line** in muted 13 px text: `[resolution_source tag] model · latency ms · N in · N out`, followed by a quiet "More" toggle that expands `key_id` and `fallback_attempts`. (Previously a boxed panel was open under every reply; in a multi-turn thread that competed with the conversation, so it was replaced.) The five required fields are therefore visible without any click, which keeps automated tests simple, while the two extra fields stay in a restrained expandable area. Values are per response, never session totals. The source is shown as text (`LIVE_INFERENCE` / `LLM_CACHE`) in a tag, not by colour alone. Test IDs:

| `data-testid` | Content |
|---|---|
| `meta-source` | `resolution_source` (`LIVE_INFERENCE` / `LLM_CACHE`, shown as a tag with text, not colour alone) |
| `meta-model` | `model` |
| `meta-latency` | `latency_ms` followed by " ms" |
| `meta-input-tokens` | `input_tokens` |
| `meta-output-tokens` | `output_tokens` |
| `meta-key` (extra, inside "More") | `key_id`, or "None (cache hit)" when null on a cache hit |
| `meta-fallback` (extra, inside "More") | `fallback_attempts` |

`meta-input-tokens` / `meta-output-tokens` contain only the number; the words "in" / "out" are outside those elements.

Other required IDs: `chat-input` (textarea, cleared immediately on send, restored if the request fails), `send-button`, `assistant-message` (one per assistant reply, including history loads), `system-prompt-input`. Extra: `user-message`.

## 8. Loading and error behaviour

- While `POST /chat` is pending: composer and send button disabled, a "Reading the conversation…" status with an animated node glyph, sidebar session/mode buttons disabled.
- While loading history: "Loading this session…", composer disabled.
- On failure the optimistic user message is removed (the backend must **not** store failed requests, as the spec says), the text is returned to the input, and a dismissible alert appears.
- HTTP **422** → "Your message must be between 1 and 4000 characters…" (when the error location is `message`) or a generic invalid-request message. Expects FastAPI's standard `{"detail":[{"loc":[...],...}]}`.
- HTTP **503** → "The analysis service is unavailable right now: every model provider failed. Try again in a moment." Expects `{"detail":"all providers unavailable"}`; the body text is not otherwise displayed.
- Network failure → "Can't reach the backend…" and the sidebar indicator turns to "unreachable".
- Other statuses show `detail` if it is a string, else "unexpected error (HTTP n)".
- After any failed send the alert also says the message is back in the input box.

## 9. Backend integration requirements and assumptions

1. **CORS:** allow the frontend origin(s) (`http://localhost:3000` and the deployed frontend URL), methods `GET, POST, OPTIONS`, header `Content-Type`. The frontend sends no auth headers and does **not** send `X-Simulate-Failure` itself (that header is for demo/curl use against the API; ask the frontend session if a UI toggle is wanted, it is deliberately out of scope).
2. Return exactly the response shapes in section 4, with `metadata` on every `/chat` response and `key_id: null` on cache hits.
3. `reply` may contain Markdown. The UI renders headings (`#`–`####`), bullets, numbered lists, `>` quotes, `**bold**`, `*italic*` and `` `code` ``. Tables and fenced code blocks are not rendered, so avoid them in prompts. The presets already ask for headings: Summary, Group patterns, Individual communication profiles, Concerns, Evidence, Suggested actions.
4. Session history returned must be oldest first and must not expose the system prompt.
5. Keep all message content under the 4000-character input rule: the UI blocks longer messages before sending.

## 10. Unresolved items

- First-wins vs latest-wins for `system_prompt` (section 6).
- Whether history will return the full metadata (section 4); the UI handles both.
- Deployment: frontend hosting target and the exact backend URL are unknown; `VITE_API_BASE_URL` must be set at build time.
- **Verified against the stub in a real browser:** welcome and workspace at desktop and mobile widths (no horizontal overflow); empty, loading (input and send disabled), reply, error (503, 422, network, stale-session 404) states; two-turn session sends only the latest message with one stable `session_id`; request bodies contain exactly `session_id`, `message`, `system_prompt`; new conversation gets a new ID; identical first message in a new session shows `LLM_CACHE` with key "None (cache hit)"; recent sessions persist across reload; reopening calls `GET /sessions/{id}/messages`, restores messages, and continuing the session reuses the same ID; editing the system prompt is what gets sent; all nine required `data-testid`s present and visible after a reply.
- **Still to verify with the real backend:** CORS, real error bodies, real cache/failover metadata, `GET /sessions/...` field presence, and the deployed `VITE_API_BASE_URL`. Suggested smoke test: send two messages in one session, reopen it from the sidebar, send an identical first message in a new session (expect `LLM_CACHE`), then use the failure-simulation header via curl (the UI has no toggle for it).
