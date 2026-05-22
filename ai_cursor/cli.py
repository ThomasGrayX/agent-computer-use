from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import time
from pathlib import Path

from ai_cursor.backends import create_desktop_backend
from ai_cursor.controller import ComputerUseRuntime
from ai_cursor.providers import create_provider


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    env_file, argv = _extract_env_file(list(argv))
    _load_env_file(env_file)

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command_name == "run":
        return _run(args)
    if args.command_name == "observe":
        return _observe(args)
    if args.command_name == "click":
        create_desktop_backend().click(args.x, args.y)
        return 0
    if args.command_name == "click-type":
        backend = create_desktop_backend()
        backend.click(args.x, args.y)
        time.sleep(args.delay)
        if args.clear:
            backend.press_key("ctrl+a")
            time.sleep(0.05)
            backend.press_key("backspace")
            time.sleep(0.05)
        backend.type_text(args.text)
        return 0
    if args.command_name == "drag":
        create_desktop_backend().drag(args.x, args.y, args.to_x, args.to_y, duration=args.duration)
        return 0
    if args.command_name == "move":
        create_desktop_backend().move(args.x, args.y)
        return 0
    if args.command_name == "type":
        create_desktop_backend().type_text(args.text)
        return 0
    if args.command_name == "key":
        create_desktop_backend().press_key(args.key)
        return 0

    parser.print_help()
    return 2


def _run(args: argparse.Namespace) -> int:
    runtime = ComputerUseRuntime(
        backend=create_desktop_backend(),
        provider=create_provider(
            args.model,
            timeout=args.model_timeout,
            max_output_tokens=args.model_output_tokens,
            reasoning_effort=args.reasoning_effort,
        ),
        artifact_root=Path(args.artifact_dir),
        target=args.target,
        allow_shell=args.allow_shell,
        cwd=Path(args.cwd).resolve(),
    )
    result = runtime.run(
        task=args.task,
        max_steps=args.max_steps,
        use_grid=args.grid,
        grid_cell=args.grid_cell,
        dry_run=args.dry_run,
        after_action_delay=args.after_action_delay,
        pre_commands=args.pre_command,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") in {"done", "dry-run", "max_steps"} else 1


def _observe(args: argparse.Namespace) -> int:
    observation = create_desktop_backend().observe(
        artifact_dir=Path(args.artifact_dir),
        step=args.step,
        use_grid=args.grid,
        grid_cell=args.grid_cell,
        target=args.target,
    )
    print(json.dumps(observation.to_dict(), indent=2))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-cursor",
        description="Let a vision LLM observe a screen and drive desktop actions.",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Load environment variables from a dotenv-style file before running.",
    )
    subparsers = parser.add_subparsers(dest="command_name")

    run = subparsers.add_parser("run", help="Run the observe/decide/act loop")
    run.add_argument("task", help="Natural-language task for the model")
    run.add_argument(
        "--model",
        default=os.environ.get("AI_CURSOR_MODEL", "mock:done"),
        help="Provider and model, for example openai:gpt-5.5 or anthropic:opus-4.7",
    )
    run.add_argument("--target", default="desktop", choices=["desktop", "ios-simulator"])
    run.add_argument("--max-steps", type=int, default=25)
    run.add_argument("--artifact-dir", default=os.environ.get("AI_CURSOR_ARTIFACT_DIR", ".ai-cursor-runs"))
    run.add_argument("--cwd", default=".")
    run.add_argument("--grid", action="store_true", help="Send a grid-overlay screenshot to the model")
    run.add_argument("--grid-cell", type=int, default=80)
    run.add_argument("--allow-shell", action="store_true", help="Allow model-requested shell commands")
    run.add_argument("--pre-command", action="append", help="Command to run before the first observation")
    run.add_argument("--dry-run", action="store_true", help="Ask the model once but do not execute the action")
    run.add_argument("--after-action-delay", type=float, default=0.8)
    run.add_argument("--model-timeout", type=float, default=120.0)
    run.add_argument(
        "--model-output-tokens",
        type=int,
        default=int(os.environ.get("AI_CURSOR_MODEL_OUTPUT_TOKENS", "4096")),
        help="Max output tokens for the model decision call.",
    )
    run.add_argument(
        "--reasoning-effort",
        default=os.environ.get("AI_CURSOR_REASONING_EFFORT", "low"),
        help="Reasoning effort for OpenAI reasoning models.",
    )

    observe = subparsers.add_parser("observe", help="Capture a screenshot and print metadata")
    observe.add_argument("--artifact-dir", default=".ai-cursor-runs/manual")
    observe.add_argument("--step", type=int, default=0)
    observe.add_argument("--target", default="desktop")
    observe.add_argument("--grid", action="store_true")
    observe.add_argument("--grid-cell", type=int, default=80)

    click = subparsers.add_parser("click", help="Click an absolute screen coordinate")
    click.add_argument("x", type=int)
    click.add_argument("y", type=int)

    click_type = subparsers.add_parser("click-type", help="Click an absolute coordinate and type text")
    click_type.add_argument("x", type=int)
    click_type.add_argument("y", type=int)
    click_type.add_argument("text")
    click_type.add_argument("--clear", action="store_true", help="Select and clear existing field text before typing")
    click_type.add_argument("--delay", type=float, default=0.15, help="Seconds to wait after click before typing")

    drag = subparsers.add_parser("drag", help="Drag between absolute screen coordinates")
    drag.add_argument("x", type=int)
    drag.add_argument("y", type=int)
    drag.add_argument("to_x", type=int)
    drag.add_argument("to_y", type=int)
    drag.add_argument("--duration", type=float, default=0.7)

    move = subparsers.add_parser("move", help="Move the cursor to an absolute screen coordinate")
    move.add_argument("x", type=int)
    move.add_argument("y", type=int)

    type_cmd = subparsers.add_parser("type", help="Type text into the active app")
    type_cmd.add_argument("text")

    key = subparsers.add_parser("key", help="Press a key or chord, for example enter or ctrl+l")
    key.add_argument("key")

    return parser


def _extract_env_file(argv: list[str]) -> tuple[Path, list[str]]:
    if "--env-file" not in argv:
        return Path(".env"), argv

    index = argv.index("--env-file")
    try:
        env_file = Path(argv[index + 1])
    except IndexError as exc:
        raise SystemExit("--env-file requires a path") from exc
    return env_file, argv[:index] + argv[index + 2 :]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        if "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _parse_env_value(value)


def _parse_env_value(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = shlex.split(value, posix=True)
    except ValueError:
        return value.strip("\"'")
    if len(parsed) == 1:
        return parsed[0]
    return value
