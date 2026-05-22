# AI Cursor Runtime

AI Cursor Runtime is a dependency-light Python CLI that lets a vision-capable LLM drive a desktop:

```text
observe screen -> ask model for one action -> execute -> observe again
```

It is meant to be called by other agents and automation scripts.

## Quick Start

```powershell
python -m ai_cursor observe --grid
python -m ai_cursor run "Open Notepad and type hello" --model openai:gpt-5.5 --grid --allow-shell
python -m ai_cursor run "Test the login flow in the iOS simulator" --model anthropic:opus-4.7 --target ios-simulator --grid --allow-shell
```

The default model is `mock:done`, which lets you verify the CLI without API keys:

```powershell
python -m ai_cursor run "Do nothing for a smoke test"
```

You can also expose the `ai-cursor` command with `pip install -e .`.

## Model Flags

Use `provider:model`:

```powershell
--model openai:gpt-5.5
--model anthropic:opus-4.7
--model mock:click-center
```

Environment variables:

```powershell
$env:OPENAI_API_KEY = "..."
$env:ANTHROPIC_API_KEY = "..."
$env:AI_CURSOR_MODEL = "openai:gpt-5.5"
$env:AI_CURSOR_MODEL_OUTPUT_TOKENS = "4096"
$env:AI_CURSOR_REASONING_EFFORT = "low"
```

The CLI also auto-loads `.env` from the current folder, so you can put those values there once. Use `--env-file path\to\file.env` if you want a different file. Real `.env` files are gitignored.

The OpenAI adapter uses the Responses API with `input_image` data URLs. The Anthropic adapter uses the Messages API with base64 image blocks.

## Commands

```powershell
python -m ai_cursor observe --grid
python -m ai_cursor click 500 400
python -m ai_cursor click-type 500 400 "hello"
python -m ai_cursor drag 140 420 900 420 --duration 0.7
python -m ai_cursor move 500 400
python -m ai_cursor type "hello"
python -m ai_cursor key ctrl+l
```

Low-level `click` and `move` commands use absolute screen coordinates. In `run`, model-returned coordinates are screenshot-local; the backend converts them to the real virtual-screen coordinate space.

## Run Loop

```powershell
python -m ai_cursor run "Open the app and verify the settings screen" `
  --model openai:gpt-5.5 `
  --grid `
  --max-steps 40 `
  --allow-shell `
  --pre-command "npm run ios"
```

Useful options:

- `--grid`: send a grid-overlay screenshot to the model for better coordinate estimates.
- `--allow-shell`: allow the model to return `run_command`.
- `--pre-command`: run a user-supplied command before the first screenshot.
- `--dry-run`: ask the model for one decision without executing it.
- `--artifact-dir`: where screenshots and `events.jsonl` are stored.
- `--model-output-tokens`: output budget for each model decision call; default is `4096`.
- `--reasoning-effort`: OpenAI reasoning effort; default is `low` so the model gets to the JSON action quickly.

## Action Contract

The model must return one JSON object:

```json
{"action":"click","x":412,"y":735,"reason":"Click the Login button"}
```

Supported actions:

- `click`
- `click_type`
- `double_click`
- `drag`
- `move`
- `type`
- `key`
- `wait`
- `run_command`
- `done`
- `fail`

Drag actions use screenshot-local coordinates:

```json
{"action":"drag","x":140,"y":420,"to_x":900,"to_y":420,"duration":0.7,"reason":"Move the icon to the right"}
```

Text-entry actions can focus a field and type:

```json
{"action":"click_type","x":412,"y":735,"text":"hello","clear":false,"reason":"Focus the search box and type hello"}
```

When the model returns `done` or `fail`, the CLI response includes `finished_state` with the final observation path, a short `screen_state`, and an `available` list for the calling agent.

## Current Backends

Windows desktop:

- screenshots are captured with PowerShell and .NET drawing APIs;
- the optional grid is drawn into a second screenshot;
- cursor and keyboard input use Windows `user32` APIs.

macOS desktop:

- screenshots are captured with the built-in `screencapture` command;
- the optional grid is drawn with a built-in PNG overlay helper;
- cursor and keyboard input use Quartz `CGEvent` APIs through Python `ctypes`;
- the terminal/Python app needs macOS Screen Recording and Accessibility permissions.

For iOS Simulator work, this MVP treats the simulator as a desktop target. The next backend should prefer simulator-native tools such as XCUITest or Appium for element-aware actions, falling back to visual clicking only when needed.

## API References

- OpenAI image input shape: <https://platform.openai.com/docs/api-reference/responses/input-items>
- Anthropic vision message blocks: <https://docs.anthropic.com/en/docs/build-with-claude/vision>

## Notes

A custom visible AI cursor is best treated as a debug overlay. The actual interaction still needs system input injection, so this runtime uses the real OS cursor for now.
