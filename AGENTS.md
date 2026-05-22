# Agent Guide: AI Cursor Runtime

This project provides a CLI that lets an agent ask a vision model to observe the desktop, choose one action, execute it, and repeat.

Use it when a task requires interacting with visible desktop UI: opening files, using Paint, moving windows, clicking app controls, dragging icons, or verifying what is on screen.

## Mental Model

Each `run` command does this loop:

```text
capture screenshot -> ask model for exactly one JSON action -> execute action -> capture again
```

The model does not receive long-term control of the machine. It gets one action at a time, and the runtime re-observes after each action.

## Basic Command

```powershell
python -m ai_cursor run "Open the picture of biscuits on the desktop." --grid --allow-shell --max-steps 25
```

Use `--grid` for almost every visual task. It overlays coordinates on the screenshot so the model can return better click and drag positions.

Use `--allow-shell` when the model may need to search the filesystem, launch an app, or run a command. Without it, the model can only act through mouse/keyboard actions.

## Platform Notes

Windows uses PowerShell/.NET for screenshots and `user32` for mouse/keyboard input.

macOS uses `screencapture` for screenshots and Quartz `CGEvent` APIs for mouse/keyboard input. The terminal or Python app that runs this CLI must have:

- Screen Recording permission for screenshots.
- Accessibility permission for clicking, dragging, and typing.

On Retina displays, screenshots may be larger than the coordinate system used for input. The macOS backend records display scale metadata and converts screenshot-local model coordinates into Quartz point coordinates.

## Model Selection

The model can be passed per run:

```powershell
python -m ai_cursor run "Task here" --model openai:gpt-5.5 --grid --allow-shell
```

```powershell
python -m ai_cursor run "Task here" --model anthropic:claude-opus-4-1-20250805 --grid --allow-shell
```

Anthropic requires real API model IDs. Do not use shorthand like `opus-4.7` unless the provider actually exposes that exact ID.

Useful Anthropic IDs:

```text
anthropic:claude-opus-4-1-20250805
anthropic:claude-opus-4-1
anthropic:claude-sonnet-4-20250514
```

The default model can be stored in `.env`:

```env
AI_CURSOR_MODEL=openai:gpt-5.5
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
```

## Model Output Settings

For OpenAI reasoning models, use low reasoning effort so the model emits the action JSON quickly:

```powershell
python -m ai_cursor run "Task here" --grid --allow-shell --reasoning-effort low --model-output-tokens 4096
```

For complex visual tasks such as drawing, increase the output budget:

```powershell
python -m ai_cursor run "Draw a heart in Paint." --grid --allow-shell --max-steps 80 --model-output-tokens 8192 --reasoning-effort low
```

If the model spends all tokens reasoning, the runtime returns a JSON failure with `finished_state` instead of crashing.

## Low-Level Commands

Use these for direct manual actions or quick actuator tests:

```powershell
python -m ai_cursor observe --grid
python -m ai_cursor click 500 400
python -m ai_cursor click-type 500 400 "hello"
python -m ai_cursor click-type 500 400 "hello" --clear
python -m ai_cursor drag 140 420 900 420 --duration 0.7
python -m ai_cursor move 500 400
python -m ai_cursor type "hello"
python -m ai_cursor key ctrl+l
```

Low-level coordinates are absolute screen coordinates. Model actions inside `run` use screenshot-local coordinates.

## Action Types

The model is instructed to return one JSON object using one of these actions:

```json
{"action":"click","x":412,"y":735,"reason":"Click the button"}
```

```json
{"action":"click_type","x":412,"y":735,"text":"hello","clear":false,"reason":"Focus the search box and type hello"}
```

```json
{"action":"double_click","x":412,"y":735,"reason":"Open the file"}
```

```json
{"action":"drag","x":140,"y":420,"to_x":900,"to_y":420,"duration":0.7,"reason":"Move the icon"}
```

```json
{"action":"type","text":"hello","reason":"Enter text"}
```

```json
{"action":"key","key":"enter","reason":"Submit"}
```

```json
{"action":"run_command","command":"start mspaint","reason":"Launch Paint"}
```

```json
{"action":"done","reason":"Task complete","screen_state":"Paint is open with a red heart on the canvas.","available":["Paint canvas","toolbar","heart drawing"]}
```

## Interpreting Results

The CLI prints JSON. Successful completion looks like:

```json
{
  "status": "done",
  "reason": "Task complete",
  "run_dir": ".ai-cursor-runs\\...",
  "steps": 4,
  "finished_state": {
    "screen_state": "The image is open in Photos.",
    "available": ["Photos window", "opened image"],
    "observation": {
      "image_path": ".ai-cursor-runs\\...\\003_screen_grid.png"
    }
  }
}
```

Use `finished_state.screen_state` and `finished_state.available` to decide the next task. Use `finished_state.observation.image_path` or the run directory if you need to inspect the last screenshot.

If `status` is `max_steps`, the runtime stopped before the model said `done` or `fail`. Increase `--max-steps`, simplify the task, or start the target app first with `--pre-command`.

If `status` is `failed`, read `reason`. Common causes:

- Invalid model ID.
- Missing API key in `.env`.
- Model ran out of output tokens before returning JSON.
- A shell command failed.
- The visible UI was not in the expected state.

## Text Entry

For a user request such as:

```text
Click the search text box and type "hello".
```

prefer a single `click_type` action when the textbox is visible:

```json
{"action":"click_type","x":640,"y":120,"text":"hello","clear":false,"reason":"Focus the search box and type hello"}
```

Use `clear=true` when the task says to replace existing text:

```json
{"action":"click_type","x":640,"y":120,"text":"hello","clear":true,"reason":"Replace the current search query with hello"}
```

If the text field is already focused, use plain `type`:

```json
{"action":"type","text":"hello","reason":"The search field is already focused"}
```

Use `key` for keyboard shortcuts and submission:

```json
{"action":"key","key":"ctrl+a","reason":"Select existing text"}
```

```json
{"action":"key","key":"enter","reason":"Submit the search"}
```

The runtime accepts common aliases from models, including `click_and_type`, `input_text`, `type_text`, `press_key`, and `hotkey`, but agents should prefer the canonical action names in this guide.

## Task Patterns

Open a desktop image:

```powershell
python -m ai_cursor run "Open the picture of biscuits on my desktop. Verify that the image is visible." --grid --allow-shell --max-steps 20
```

Draw in Paint when Paint is already open and the pencil is selected:

```powershell
python -m ai_cursor run "Draw a simple red heart in the center of the Paint canvas using drag strokes. Use one drag stroke per step." --grid --allow-shell --max-steps 80 --model-output-tokens 8192 --reasoning-effort low
```

Open Paint first, then draw:

```powershell
python -m ai_cursor run "Draw a simple red heart in the center of the Paint canvas using drag strokes." --pre-command "start mspaint" --grid --allow-shell --max-steps 80 --model-output-tokens 8192 --reasoning-effort low
```

Move a desktop icon:

```powershell
python -m ai_cursor run "Drag the biscuits icon from the left side of the desktop to the right side. Verify the new location." --grid --allow-shell --max-steps 20
```

Click a search box and type a query:

```powershell
python -m ai_cursor run "Click the visible search text box and type \"hello\". Then report what is visible." --grid --allow-shell --max-steps 10
```

## Practical Advice

Prefer concrete, visible tasks. Good:

```text
Click the Save button.
Drag the biscuits icon to the right side of the desktop.
Draw a simple heart in the center of the Paint canvas using drag strokes.
```

Avoid broad tasks that require many hidden assumptions. Break them into smaller runs:

```text
Open Paint.
Select the pencil.
Draw a heart.
Save the file to Desktop.
```

For drawing tasks, explicitly say the tool is already selected if it is:

```text
Paint is already open and the pencil is selected. Draw a simple red heart in the center of the canvas using drag strokes.
```

Keep `--grid` on. It is the most important reliability boost for visual clicking and dragging.
