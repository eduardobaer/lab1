# Spider — Android App Documentation Crawler

Spider takes a published Android app (APK) and produces a maximally detailed PRD by autonomously navigating the app on an emulator and documenting everything Claude can observe.

## Quick start

### Prerequisites

- Python 3.11+
- Android SDK platform-tools on `PATH` (provides `adb`)
- An Android emulator booted, e.g.:
  ```
  emulator -avd Pixel_5_API_33
  ```
- An `ANTHROPIC_API_KEY` for Claude

### Install

```bash
pip install -e .
```

### Configure

```bash
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY
```

### Run

```bash
spider explore path/to/app.apk --max-steps 200
```

This will:
1. Install the APK on the connected emulator
2. Launch the app
3. Drive Claude through up to 200 steps of exploration
4. Synthesize a comprehensive PRD

Outputs land in `runs/<timestamp>-<package>/`:

| File | Contents |
|---|---|
| `prd.md` | Human-readable PRD |
| `graph.json` | Full state graph (nodes, edges, exploration status) |
| `observations.json` | Structured screen/flow documentation Claude recorded |
| `screenshots/` | One PNG per discovered screen |
| `hierarchies/` | UI hierarchy XML per screen |
| `trace.jsonl` | Per-step trace including LLM reasoning + token usage |
| `config.json` | The run config |

### Regenerate the PRD only

If you want to re-run PRD synthesis without re-exploring (e.g. after improving the prompt):

```bash
spider prd runs/20260502-...-com.example.app/
```

## Architecture

```
APK ──▶ Device (uiautomator2) ──▶ Screen capture (screenshot + XML)
                                          │
                                          ▼
                                  Screen Graph (dedup via pHash + structural hash)
                                          │
                                          ▼
                                  LLM Explorer (Claude Opus 4.7, vision + tools)
                                          │
                                          ▼
                                  Action (tap / swipe / type / record_*)
                                          │
                                          ▼
                                  ... loop until budget / saturation ...
                                          │
                                          ▼
                                  PRD Generator (Claude Opus 4.7 with effort=max, streamed)
```

Each exploration step rebuilds the prompt from scratch (stateless from Claude's
POV) — the loop is the agent, Claude is the policy. This keeps token usage flat
across thousands of steps. Prompt caching keeps the system prompt + tool
definitions warm.

## Cost

Spider uses Claude Opus 4.7 by default. A typical 200-step run with prompt
caching enabled costs roughly $3–$8 in API tokens, depending on app complexity.
To reduce cost, pass `--model claude-sonnet-4-6`.

## Limitations (v1)

- **Network capture**: not yet implemented. The PRD's "API contracts" section is
  inferred from UI behavior only. v2 will integrate `mitmproxy` to capture
  HTTPS traffic and document real endpoints.
- **Login walls**: Spider cannot log in for you. If the app requires
  authentication, sign in manually on the emulator before running, or the
  explorer will document only the unauthenticated surface.
- **Destructive actions**: Spider is instructed to avoid Delete, Sign out, Pay,
  etc. It will document them but not activate them.
- **iOS**: not supported.
