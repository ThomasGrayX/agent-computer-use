---
name: agent-computer-use
description: Vision-driven desktop automation for macOS and Windows. Use when a task requires interacting with visible UI — opening files, driving apps, clicking controls, dragging icons, verifying what's on screen, or testing iOS simulator flows by sight. Drives the desktop via a one-action-at-a-time observe→act→observe loop with a vision LLM (OpenAI or Anthropic). Triggers on phrases like "drive the desktop", "have the model click X", "use computer-use", "screenshot and click", "automate the UI".
---

# Agent Computer Use

Python CLI that lets a vision LLM observe the desktop, choose **one** JSON action, execute it, and re-observe.

## Install

```bash
git clone https://github.com/ThomasGrayX/agent-computer-use.git
cd agent-computer-use
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env  # fill in OPENAI_API_KEY and/or ANTHROPIC_API_KEY
```

Requires Python 3.11+.

After `pip install -e .`, the `ai-cursor` command is on the venv's PATH. The examples below use `python -m ai_cursor` so they work without activating the venv — replace with `.venv/bin/ai-cursor` if you prefer.

## Platform setup

### macOS

`screencapture` lives at `/usr/sbin/screencapture`. If your shell or agent harness omits `/usr/sbin` from PATH, prefix calls with `PATH="/usr/sbin:$PATH"`.

Grant the terminal (or the Python binary in `.venv/bin/`) two permissions:

1. **System Settings → Privacy & Security → Screen Recording** — required for `screencapture`. Without it: `could not create image from display`.
2. **System Settings → Privacy & Security → Accessibility** — required for `CGEvent` mouse/keyboard injection. Without it: clicks/drags silently do nothing.

The first call that needs each permission will trigger the OS prompt.

### Windows

No extra permissions — screenshots use PowerShell/.NET, input uses `user32`.

## Mental model

```
screencapture → model returns ONE JSON action → runtime executes → screencapture again
```

The model never gets long-term control of the machine. Every step re-observes. The loop stops when the model returns `done`/`fail` or `--max-steps` is hit.

## Default invocation

Almost every run wants `--grid` (coordinate overlay = far better clicks) and `--allow-shell` (lets the model launch apps / run shell commands).

```bash
python -m ai_cursor run \
  "Open the picture of biscuits on the desktop." \
  --grid --allow-shell --max-steps 25
```

## Model selection

Pass `provider:model`. Use real API IDs — no shorthand.

```bash
--model openai:gpt-5.5
--model anthropic:claude-opus-4-1-20250805
--model anthropic:claude-sonnet-4-20250514
```

Or set `AI_CURSOR_MODEL` in `.env`. Default is `mock:done` (no-op smoke test).

For OpenAI reasoning models, keep effort low so it emits JSON fast:

```bash
--reasoning-effort low --model-output-tokens 4096
```

For drawing / many-step visual work, raise the output budget:

```bash
--max-steps 80 --model-output-tokens 8192 --reasoning-effort low
```

## Low-level commands (manual / actuator tests)

```bash
python -m ai_cursor observe --grid
python -m ai_cursor click 500 400
python -m ai_cursor click-type 500 400 "hello" [--clear]
python -m ai_cursor drag 140 420 900 420 --duration 0.7
python -m ai_cursor move 500 400
python -m ai_cursor type "hello"
python -m ai_cursor key cmd+space
```

Low-level coords are absolute screen coordinates. `run`-loop model actions use **screenshot-local** coords; the backend converts via `scale_x`/`scale_y` from observation metadata (so Retina displays work transparently).

## Action JSON the model returns

One of: `click`, `click_type`, `double_click`, `drag`, `move`, `type`, `key`, `wait`, `run_command`, `done`, `fail`. Examples:

```json
{"action":"click","x":412,"y":735,"reason":"Click the button"}
{"action":"click_type","x":412,"y":735,"text":"hello","clear":false,"reason":"Focus + type"}
{"action":"drag","x":140,"y":420,"to_x":900,"to_y":420,"duration":0.7,"reason":"Move icon"}
{"action":"key","key":"cmd+a","reason":"Select all"}
{"action":"run_command","command":"open -a Preview ~/Desktop/biscuits.png","reason":"Launch Preview"}
{"action":"done","reason":"Task complete","screen_state":"Preview open with biscuits image.","available":["Preview window","image"]}
```

Aliases like `click_and_type`, `press_key`, `hotkey`, `input_text`, `type_text` are accepted but agents should prefer the canonical names.

### macOS key tokens

`cmd`/`command`/`win`, `ctrl`/`control`, `shift`, `alt`/`option`, `enter`/`return`, `tab`, `escape`/`esc`, `backspace`/`delete`, `forward_delete`, `space`, arrow keys, `home`, `end`, `pageup`, `pagedown`, `f1`–`f12`, letters, numbers, common punctuation. Map per `ai_cursor/backends/macos.py`.

## Reading the result

CLI prints JSON. Success:

```json
{
  "status": "done",
  "reason": "...",
  "run_dir": ".ai-cursor-runs/...",
  "steps": 4,
  "finished_state": {
    "screen_state": "Image open in Preview.",
    "available": ["Preview window", "opened image"],
    "observation": { "image_path": ".ai-cursor-runs/.../003_screen_grid.png" }
  }
}
```

- `status: max_steps` → loop ran out. Bump `--max-steps`, simplify the task, or pre-launch the app with `--pre-command`.
- `status: failed` → read `reason`. Common: bad model ID, missing API key, output-token starvation, shell failure, unexpected UI state, missing Screen Recording / Accessibility permission.

Use `finished_state.screen_state` + `available` to decide the next task. Last screenshot is at `finished_state.observation.image_path`.

## Common task patterns

```bash
# Open a desktop image
python -m ai_cursor run "Open the picture of biscuits on my desktop. Verify it's visible." \
  --grid --allow-shell --max-steps 20

# Launch Preview then act
python -m ai_cursor run "Resize the image to 800px wide using Tools → Adjust Size." \
  --pre-command "open -a Preview ~/Desktop/biscuits.png" \
  --grid --allow-shell --max-steps 40

# Move a desktop icon
python -m ai_cursor run "Drag the biscuits icon from the left to the right side of the desktop. Verify the new location." \
  --grid --allow-shell --max-steps 20

# Click a search box and type
python -m ai_cursor run "Click the visible search text box and type \"hello\". Report what is visible." \
  --grid --allow-shell --max-steps 10
```

## Practical advice

- Always keep `--grid` on. Biggest reliability boost.
- Prefer concrete, visible tasks ("Click the Save button") over broad ones ("Set up the app").
- Break complex flows into multiple runs. Each `done` returns enough state for the next.
- If a tool is preselected, **say so** in the prompt.
- For text entry, prefer single `click_type` over click→type when the target is visible. Use `clear:true` to replace existing text.
- iOS-simulator work uses the same visual loop — the simulator just looks like another window.
- macOS coordinates are in **points** at the screen level; screenshot coords from `screencapture` are in **pixels**. The runtime computes `scale_x`/`scale_y` from the main display and converts automatically.

## Env vars

```env
AI_CURSOR_MODEL=openai:gpt-5.5
AI_CURSOR_MODEL_OUTPUT_TOKENS=4096
AI_CURSOR_REASONING_EFFORT=low
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
```

`.env` is auto-loaded from cwd; pass `--env-file` to override. `.env` is gitignored — never commit credentials.

## Known papercuts

- macOS: `screencapture` not on the harness PATH. Prefix `PATH="/usr/sbin:$PATH"` when invoking from agent shells that strip it.
- First-time Screen Recording / Accessibility prompts will only appear after the **first** call that needs them; if denied, the call errors with a specific message.
