---
name: testing-jarvis
description: How to run and end-to-end test the Jarvis voice assistant (FastAPI backend + Vite/Three.js hologram frontend) in a browser, including the timers/tools path and known rendering pitfalls.
---

# Testing Jarvis end-to-end

## Bring the app up (no credentials needed)
```bash
# backend on 127.0.0.1:8000 — offline rule brain when JARVIS_API_KEY is unset
cd backend && setsid nohup .venv/bin/python -m jarvis > /tmp/uvicorn.log 2>&1 < /dev/null &
# frontend on localhost:5173 (vite proxies /api and /ws to the backend)
cd frontend && npm run dev
```
- `curl 127.0.0.1:8000/api/config` is the quickest health/feature probe: it reports
  `chat_model` (`local-rules` when offline) and the registered `tools` list.
- Do NOT set `JARVIS_API_KEY` for offline testing: the browser handles speech and
  `tools/intents.py:match_intent()` does phrase matching instead of model function calls.
- Kill/restart carefully: `pkill -f "python -m jarvis"` in the *same* shell command that
  backgrounds the new server can kill the new process too. Run them as separate calls.

## Origin allowlist (important when serving from a non-default port)
The websocket handshake checks `Origin` itself (`config.py: origin_allowed`). Default allowlist is
`http://localhost:5173` / `http://127.0.0.1:5173` only. If you serve the frontend on another port
(e.g. a git worktree of an older commit for a regression comparison on 5174), the socket closes
immediately and the UI shows the connection badge as `closed`. Fix:
```bash
JARVIS_CORS_ORIGINS="http://localhost:5173,http://localhost:5174" .venv/bin/python -m jarvis
```

## UI path
- Command input: `aria-label="Command"` text box at the bottom (`components/Console.tsx`), Enter submits.
  Typing commands is the reliable way to drive tests — there is usually no microphone on a cloud box,
  and clicking `talk` then yields the banner "Microphone access was denied." (mark voice UNTESTED).
- Buttons: `talk`, `silence`, `clear` (clear = reset), plus a `require "jarvis"` wake-word checkbox.
- State badge (`standing by` / `listening` / `thinking` / `speaking`) sits above the input; the
  fps + quality tier readout is top-right (`hide stats` toggles it).
- Quality tier is chosen from `navigator.hardwareConcurrency`, so a 2-core box starts at `lite`
  legitimately — that is not a perf regression. Expect ~20-60 fps with software GL.

## Regression to watch: short replies must render in the transcript
`useJarvis.ts` builds the assistant turn from `token` frames and finalises it on `reply_end`. React
batches those `setTurns` updaters, so anything that reads `streamingIdRef` *inside* an updater sees
the value `reply_end` already cleared and the whole line silently disappears. Replies short enough to
arrive in one batch (`42`, `It is 07:38.`, `Timer 1 set for 10 seconds (tea timer).`) are the ones
that break; long replies (system status, search results) span frames and hide the bug. Always spot
check one short reply. If it regresses, compare against the base commit before blaming a PR.

Ways to inspect replies independently of the UI:
- Temporarily slow the offline token stream: `registry.py` → `LocalLLM(chunk_delay=0.25)`, restart the
  backend. Revert afterwards.
- Or read the frames directly with a websocket probe:
```python
import asyncio, json, websockets
async def main():
    async with websockets.connect("ws://127.0.0.1:8000/ws", origin="http://localhost:5173") as ws:
        await ws.send(json.dumps({"type": "user_text", "text": "set a tea timer for 5 seconds"}))
        while True: print(await ws.recv())
asyncio.run(main())
```

## Timers / tools specifics
- Timers are per-websocket-connection: reloading the tab drops all pending timers (by design).
- A timer that elapses arrives as a server->client `notice` frame; the frontend appends it as its own
  transcript line and speaks it, so the spontaneous "Your <label> is up." line is independent of the
  normal streaming reply path.
- Useful offline phrasings: `set a tea timer for 10 seconds`, `what timers are running`,
  `cancel timer 2`, `cancel all timers`, `system status`, `search the web for <query>`.
- `web_search` hits `https://html.duckduckgo.com/html/` — check egress first with
  `curl -m 15 -X POST https://html.duckduckgo.com/html/ -d q=test -A Mozilla/5.0`.

## Devin Secrets Needed
None for offline testing. `JARVIS_API_KEY` (and optionally `JARVIS_SEARCH_API_KEY` for the Brave
search path) would be required to test the cloud LLM / server STT+TTS / Brave branches.
