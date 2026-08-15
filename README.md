# JARVIS

A voice assistant with a holographic front end: a WebGL orb that listens, thinks
and talks, backed by a FastAPI core with swappable speech and language providers.

```
frontend/   Vite + React + three.js hologram HUD
backend/    FastAPI websocket core (LLM / STT / TTS providers)
```

It runs with **zero configuration** — the browser handles speech recognition and
synthesis and a local rule engine answers simple questions. Add an API key and
the same UI is driven by a real model with cloud transcription and voice.

## Quick start

```bash
# core
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m jarvis            # http://127.0.0.1:8000

# hologram
cd ../frontend
npm install
npm run dev                           # http://localhost:5173
```

Open the UI, press **talk**, and say `jarvis, what is the time`. Untick
*require "jarvis"* to drop the wake word and talk continuously.

## Configuration

Everything is environment driven; nothing is required.

| Variable | Default | Purpose |
| --- | --- | --- |
| `JARVIS_API_KEY` | – | Enables the OpenAI-compatible providers. Without it the local rule engine answers. |
| `JARVIS_API_BASE` | `https://api.openai.com/v1` | Any compatible endpoint (Ollama, vLLM, LM Studio, a gateway). |
| `JARVIS_CHAT_MODEL` | `gpt-4o-mini` | Chat model. |
| `JARVIS_STT_MODEL` | `whisper-1` | Server-side transcription model. |
| `JARVIS_TTS_MODEL` / `JARVIS_TTS_VOICE` | `gpt-4o-mini-tts` / `onyx` | Server-side voice. |
| `JARVIS_SERVER_TTS` | `true` | Set `false` to always speak with the browser voice. |
| `JARVIS_WAKE_WORD` | `jarvis` | Wake word the UI listens for. |
| `JARVIS_SYSTEM_PROMPT` | terse JARVIS persona | Personality. |
| `JARVIS_HISTORY_TURNS` | `12` | Conversation turns kept in context. |
| `JARVIS_CORS_ORIGINS` | `http://localhost:5173,…` | Allowed browser origins (also checked on the websocket handshake). |
| `JARVIS_SEARCH_API_KEY` | – | Brave Search key. Without it `web_search` scrapes DuckDuckGo's HTML endpoint. |
| `JARVIS_MAX_TOOL_ROUNDS` | `3` | Cap on tool-call round trips per reply. |

The client discovers which capabilities exist at connect time (`hello` frame) and
adapts: server transcription when available, otherwise the Web Speech API;
server voice when available, otherwise `speechSynthesis`.

## Skills and tools

The same tools are available to both brains: the cloud model gets them as
function specs, and the offline rule engine reaches them through phrase matching
(`set a timer for 5 minutes`, `what timers are running`, `cancel timer 2`,
`system status`, `search the web for …`).

| Tool | Notes |
| --- | --- |
| `set_timer` / `list_timers` / `cancel_timer` | Per-connection countdowns (max 16, max 24h). When one elapses the server pushes a `notice` frame and JARVIS speaks it unprompted. |
| `system_info` | Platform, CPUs, load, memory, disk, uptime — read from the standard library only, never the environment. |
| `web_search` | Brave Search when `JARVIS_SEARCH_API_KEY` is set, otherwise DuckDuckGo's no-key HTML endpoint. Runs on an unauthenticated HTTP client so the LLM key is never sent to a search host. |

Timers belong to the websocket session, so closing the tab cancels them.

## How the hologram stays smooth

The "must not lag" requirement drove the rendering design:

- **No per-frame React.** Loudness and assistant state are written into a plain
  mutable `HologramSignals` object; the render loop reads it directly. React only
  re-renders on transcript changes.
- **All motion in GLSL.** Orb deformation, HUD ring sweeps and particle orbits
  are computed in shaders from a handful of uniforms — the CPU pushes numbers,
  never geometry.
- **Adaptive quality.** `PerfGuard` measures frame rate in one-second windows and
  moves between four tiers (mesh subdivision, particle count, pixel-ratio cap).
  It drops a tier after two slow windows, and only climbs after six fast ones, so
  quality never oscillates visibly.
- **Cheap compositing.** Additive blending with no post-processing pass, no
  shadows, no lights, `depthWrite: false`, antialiasing off, device pixel ratio
  capped per tier. The HUD grid is CSS, not geometry.
- **Idle discipline.** Rendering stops on `visibilitychange`, delta time is
  clamped so a background tab cannot produce a jump, and geometry is disposed on
  every tier change.

The **fps / tier** readout in the top right shows what the guard has settled on.

## Protocol

One websocket at `/ws`, JSON frames both ways.

| Client | Server |
| --- | --- |
| `user_text`, `user_audio`, `cancel`, `reset`, `ping` | `hello`, `state`, `transcript`, `token`, `reply_end`, `audio`, `notice`, `error`, `pong` |

`state` drives the hologram's colour and turbulence
(`idle`/`listening`/`thinking`/`speaking`); `token` frames stream the reply as it
is generated. `notice` frames are unsolicited (a fired timer) and carry `speak`,
which is `false` when server audio follows.

## Development

```bash
cd backend  && .venv/bin/python -m pytest && .venv/bin/ruff check . && .venv/bin/mypy
cd frontend && npm run lint && npm run build
```
