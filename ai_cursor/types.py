from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


VALID_ACTIONS = {
    "click",
    "click_type",
    "double_click",
    "drag",
    "move",
    "type",
    "key",
    "wait",
    "run_command",
    "done",
    "fail",
    "noop",
}

ACTION_ALIASES = {
    "click_and_type": "click_type",
    "click-then-type": "click_type",
    "click_then_type": "click_type",
    "input": "type",
    "input_text": "type",
    "type_text": "type",
    "press": "key",
    "press_key": "key",
    "hotkey": "key",
}


@dataclass
class Observation:
    screenshot_path: Path
    width: int
    height: int
    left: int = 0
    top: int = 0
    grid_path: Path | None = None
    target: str = "desktop"
    step: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def image_path(self) -> Path:
        return self.grid_path or self.screenshot_path

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["screenshot_path"] = str(self.screenshot_path)
        data["grid_path"] = str(self.grid_path) if self.grid_path else None
        data["image_path"] = str(self.image_path)
        return data


@dataclass
class ActionDecision:
    action: str
    x: int | None = None
    y: int | None = None
    text: str | None = None
    key: str | None = None
    command: str | None = None
    clear: bool = False
    seconds: float | None = None
    duration: float | None = None
    to_x: int | None = None
    to_y: int | None = None
    reason: str | None = None
    screen_state: str | None = None
    available: list[str] = field(default_factory=list)
    confidence: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActionDecision":
        action = str(data.get("action", "noop")).strip().lower()
        action = ACTION_ALIASES.get(action, action)
        if action not in VALID_ACTIONS:
            action = "noop"
        return cls(
            action=action,
            x=_optional_int(data.get("x")),
            y=_optional_int(data.get("y")),
            text=_optional_str(data.get("text")),
            key=_optional_str(data.get("key")),
            command=_optional_str(data.get("command")),
            clear=_optional_bool(data.get("clear")),
            seconds=_optional_float(data.get("seconds")),
            duration=_optional_float(data.get("duration")),
            to_x=_optional_int(_first_present(data, "to_x", "end_x", "x2")),
            to_y=_optional_int(_first_present(data, "to_y", "end_y", "y2")),
            reason=_optional_str(data.get("reason")),
            screen_state=_optional_str(data.get("screen_state")),
            available=_optional_string_list(data.get("available")),
            confidence=_optional_float(data.get("confidence")),
            raw=data,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActionResult:
    action: str
    success: bool
    message: str = ""
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


History = list[dict[str, Any]]


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _optional_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _first_present(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return None
