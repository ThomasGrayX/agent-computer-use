from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

from ai_cursor.backends import DesktopBackend
from ai_cursor.providers.base import ModelProvider
from ai_cursor.types import ActionDecision, ActionResult, History, Observation


class ComputerUseRuntime:
    def __init__(
        self,
        backend: DesktopBackend,
        provider: ModelProvider,
        artifact_root: Path,
        target: str = "desktop",
        allow_shell: bool = False,
        cwd: Path | None = None,
    ) -> None:
        self.backend = backend
        self.provider = provider
        self.artifact_root = artifact_root
        self.target = target
        self.allow_shell = allow_shell
        self.cwd = cwd or Path.cwd()

    def run(
        self,
        task: str,
        max_steps: int = 25,
        use_grid: bool = False,
        grid_cell: int = 80,
        dry_run: bool = False,
        after_action_delay: float = 0.8,
        pre_commands: list[str] | None = None,
    ) -> dict:
        run_dir = self._create_run_dir()
        events_path = run_dir / "events.jsonl"
        history: History = []

        for pre_command in pre_commands or []:
            result = _run_command(pre_command, self.cwd)
            _append_event(
                events_path,
                {"type": "pre_command", "command": pre_command, "result": result.to_dict()},
            )
            if not result.success:
                return {"status": "failed", "reason": f"pre-command failed: {pre_command}", "run_dir": str(run_dir)}

        for step in range(max_steps):
            observation = self.backend.observe(
                run_dir,
                step=step,
                use_grid=use_grid,
                grid_cell=grid_cell,
                target=self.target,
            )
            try:
                decision = self.provider.decide(task, observation, history, self.allow_shell)
            except Exception as exc:
                _append_event(
                    events_path,
                    {
                        "type": "model_error",
                        "step": step,
                        "observation": observation.to_dict(),
                        "error": str(exc),
                    },
                )
                return {
                    "status": "failed",
                    "reason": str(exc),
                    "run_dir": str(run_dir),
                    "steps": step + 1,
                    "finished_state": {
                        "screen_state": "Model failed before returning an action.",
                        "available": [],
                        "observation": observation.to_dict(),
                    },
                }

            if dry_run:
                result = ActionResult(action=decision.action, success=True, message="dry-run: action not executed")
                _append_step(events_path, step, observation, decision, result)
                return {"status": "dry-run", "decision": decision.to_dict(), "run_dir": str(run_dir)}

            result = self._execute(decision, observation)
            item = _append_step(events_path, step, observation, decision, result)
            history.append(item)

            if decision.action == "done":
                return _terminal_result("done", decision, observation, run_dir, step + 1)
            if decision.action == "fail":
                return _terminal_result("failed", decision, observation, run_dir, step + 1)

            time.sleep(after_action_delay)

        final_observation = history[-1]["observation"] if history else None
        return {
            "status": "max_steps",
            "reason": f"Stopped after {max_steps} steps",
            "run_dir": str(run_dir),
            "steps": max_steps,
            "finished_state": {
                "screen_state": "Stopped before the model returned done or fail.",
                "available": [],
                "observation": final_observation,
            },
        }

    def _execute(self, decision: ActionDecision, observation: Observation) -> ActionResult:
        try:
            if decision.action == "click":
                _require_coords(decision)
                self.backend.click(decision.x, decision.y, observation)
                return ActionResult("click", True, f"clicked {decision.x},{decision.y}")
            if decision.action == "click_type":
                _require_coords(decision)
                if decision.text is None:
                    raise ValueError("click_type action requires text")
                self.backend.click(decision.x, decision.y, observation)
                time.sleep(0.15)
                if decision.clear:
                    self.backend.press_key("ctrl+a")
                    time.sleep(0.05)
                    self.backend.press_key("backspace")
                    time.sleep(0.05)
                self.backend.type_text(decision.text)
                return ActionResult(
                    "click_type",
                    True,
                    f"clicked {decision.x},{decision.y} and typed {len(decision.text)} characters",
                )
            if decision.action == "double_click":
                _require_coords(decision)
                self.backend.double_click(decision.x, decision.y, observation)
                return ActionResult("double_click", True, f"double-clicked {decision.x},{decision.y}")
            if decision.action == "move":
                _require_coords(decision)
                self.backend.move(decision.x, decision.y, observation)
                return ActionResult("move", True, f"moved to {decision.x},{decision.y}")
            if decision.action == "drag":
                _require_drag_coords(decision)
                duration = decision.duration if decision.duration is not None else 0.7
                self.backend.drag(decision.x, decision.y, decision.to_x, decision.to_y, observation, duration)
                return ActionResult("drag", True, f"dragged {decision.x},{decision.y} to {decision.to_x},{decision.to_y}")
            if decision.action == "type":
                if decision.text is None:
                    raise ValueError("type action requires text")
                self.backend.type_text(decision.text)
                return ActionResult("type", True, f"typed {len(decision.text)} characters")
            if decision.action == "key":
                if not decision.key:
                    raise ValueError("key action requires key")
                self.backend.press_key(decision.key)
                return ActionResult("key", True, f"pressed {decision.key}")
            if decision.action == "wait":
                seconds = max(0.0, min(float(decision.seconds or 1.0), 30.0))
                time.sleep(seconds)
                return ActionResult("wait", True, f"waited {seconds:.2f}s")
            if decision.action == "run_command":
                if not self.allow_shell:
                    return ActionResult("run_command", False, "run_command rejected because --allow-shell is off")
                if not decision.command:
                    raise ValueError("run_command action requires command")
                return _run_command(decision.command, self.cwd)
            if decision.action in {"done", "fail", "noop"}:
                return ActionResult(decision.action, True, decision.reason or "")
            return ActionResult(decision.action, False, f"unsupported action {decision.action}")
        except Exception as exc:
            return ActionResult(decision.action, False, str(exc))

    def _create_run_dir(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = self.artifact_root / stamp
        path.mkdir(parents=True, exist_ok=False)
        return path


def _run_command(command: str, cwd: Path) -> ActionResult:
    completed = subprocess.run(command, shell=True, cwd=str(cwd), capture_output=True, text=True, timeout=120)
    return ActionResult(
        action="run_command",
        success=completed.returncode == 0,
        message=f"exit {completed.returncode}",
        stdout=completed.stdout[-8000:],
        stderr=completed.stderr[-8000:],
        returncode=completed.returncode,
    )


def _append_step(
    events_path: Path,
    step: int,
    observation: Observation,
    decision: ActionDecision,
    result: ActionResult,
) -> dict:
    item = {
        "type": "step",
        "step": step,
        "observation": observation.to_dict(),
        "decision": decision.to_dict(),
        "result": result.to_dict(),
    }
    _append_event(events_path, item)
    return item


def _append_event(events_path: Path, item: dict) -> None:
    with events_path.open("a", encoding="utf-8") as handle:
        json.dump(item, handle, ensure_ascii=True)
        handle.write("\n")


def _require_coords(decision: ActionDecision) -> None:
    if decision.x is None or decision.y is None:
        raise ValueError(f"{decision.action} action requires x and y")


def _require_drag_coords(decision: ActionDecision) -> None:
    if decision.x is None or decision.y is None or decision.to_x is None or decision.to_y is None:
        raise ValueError("drag action requires x, y, to_x, and to_y")


def _terminal_result(
    status: str,
    decision: ActionDecision,
    observation: Observation,
    run_dir: Path,
    steps: int,
) -> dict:
    return {
        "status": status,
        "reason": decision.reason,
        "run_dir": str(run_dir),
        "steps": steps,
        "finished_state": {
            "screen_state": decision.screen_state or decision.reason or "",
            "available": decision.available,
            "observation": observation.to_dict(),
        },
    }
