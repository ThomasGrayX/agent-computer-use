from __future__ import annotations

import json
from abc import ABC, abstractmethod

from ai_cursor.types import ActionDecision, History, Observation


SYSTEM_PROMPT = """You are an AI computer-use controller.

Your job is to choose exactly one next action for a local automation runtime.
Return only a JSON object. Do not wrap it in Markdown.
Prefer the smallest useful visible action. If the requested task can be advanced
with one obvious click, drag, keypress, or typed text, return that action now
instead of planning the whole task.

Coordinate rules:
- Use screenshot-local pixel coordinates.
- The screenshot origin is top-left: x=0, y=0.
- Do not use OS absolute monitor coordinates.
- If a grid overlay is present, use it only to estimate screenshot-local coordinates.

Allowed actions:
- click: {"action":"click","x":123,"y":456,"reason":"..."}
- click_type: {"action":"click_type","x":123,"y":456,"text":"hello","clear":false,"reason":"..."}
- double_click: {"action":"double_click","x":123,"y":456,"reason":"..."}
- drag: {"action":"drag","x":123,"y":456,"to_x":700,"to_y":456,"duration":0.7,"reason":"..."}
- move: {"action":"move","x":123,"y":456,"reason":"..."}
- type: {"action":"type","text":"hello","reason":"..."}
- key: {"action":"key","key":"enter","reason":"..."}
- wait: {"action":"wait","seconds":1.0,"reason":"..."}
- run_command: {"action":"run_command","command":"...","reason":"..."}
- done: {"action":"done","reason":"task complete","screen_state":"what is visible now","available":["useful visible controls or files"]}
- fail: {"action":"fail","reason":"why the task cannot continue","screen_state":"what is visible now","available":["useful visible controls or files"]}

For text entry, if the target field is not focused, use click_type with the field
coordinate and text. If the field is already focused, use type. Use clear=true
when replacing existing text in a field. Use key for shortcuts such as ctrl+a,
enter, tab, escape, or ctrl+l.
For drag, x/y is the point to press and to_x/to_y is the point to release.
For drawing tasks, if a drawing app is already open and the tool/canvas is ready,
draw with direct drag strokes. Use one drag stroke per step and let the runtime
observe before the next stroke.
After a click, drag, or command, expect the runtime to observe the screen again
before you choose another action. When returning done or fail, include a concise
screen_state and available list for the agent that called you. Be precise and
conservative."""


class ModelProvider(ABC):
    name = "base"

    def __init__(
        self,
        model: str,
        timeout: float = 120.0,
        max_output_tokens: int = 4096,
        reasoning_effort: str | None = "low",
    ):
        self.model = model
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort

    @abstractmethod
    def decide(
        self,
        task: str,
        observation: Observation,
        history: History,
        allow_shell: bool,
    ) -> ActionDecision:
        """Return the next action decision."""


def build_decision_prompt(
    task: str,
    observation: Observation,
    history: History,
    allow_shell: bool,
) -> str:
    history_tail = [
        {
            "step": item.get("step"),
            "decision": item.get("decision"),
            "result": item.get("result"),
        }
        for item in history[-8:]
    ]
    shell_note = (
        "Shell commands are allowed when useful."
        if allow_shell
        else "Shell commands are not allowed; do not choose run_command."
    )
    grid_note = (
        "A grid overlay is visible in the image. It is for coordinate estimation only."
        if observation.grid_path
        else "No grid overlay is visible."
    )

    return f"""Task:
{task}

Target:
{observation.target}

Current screenshot:
- width: {observation.width}
- height: {observation.height}
- origin: top-left screenshot pixel
- virtual screen offset: left={observation.left}, top={observation.top}
- {grid_note}
- {shell_note}

Recent history:
{json.dumps(history_tail, ensure_ascii=True, indent=2)}

Return one JSON object for the next action."""
