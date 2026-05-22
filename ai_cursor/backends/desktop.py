from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from pathlib import Path

from ai_cursor.types import Observation


class DesktopBackend(ABC):
    @abstractmethod
    def observe(
        self,
        artifact_dir: Path,
        step: int,
        use_grid: bool = False,
        grid_cell: int = 80,
        target: str = "desktop",
    ) -> Observation:
        """Capture the current screen."""

    @abstractmethod
    def move(self, x: int, y: int, observation: Observation | None = None) -> None:
        """Move the system cursor."""

    @abstractmethod
    def click(self, x: int, y: int, observation: Observation | None = None) -> None:
        """Click at a coordinate."""

    @abstractmethod
    def double_click(self, x: int, y: int, observation: Observation | None = None) -> None:
        """Double-click at a coordinate."""

    @abstractmethod
    def drag(
        self,
        x: int,
        y: int,
        to_x: int,
        to_y: int,
        observation: Observation | None = None,
        duration: float = 0.7,
    ) -> None:
        """Drag from one coordinate to another."""

    @abstractmethod
    def type_text(self, text: str) -> None:
        """Type text into the active application."""

    @abstractmethod
    def press_key(self, key: str) -> None:
        """Press a key or key chord such as ctrl+l."""


def create_desktop_backend() -> DesktopBackend:
    if sys.platform == "win32":
        from ai_cursor.backends.windows import WindowsDesktopBackend

        return WindowsDesktopBackend()
    if sys.platform == "darwin":
        from ai_cursor.backends.macos import MacOSDesktopBackend

        return MacOSDesktopBackend()
    raise RuntimeError(f"Desktop backend is currently implemented for Windows and macOS, not {sys.platform}.")
