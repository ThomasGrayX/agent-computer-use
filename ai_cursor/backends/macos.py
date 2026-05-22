from __future__ import annotations

import ctypes
import shutil
import subprocess
import time
from pathlib import Path

from ai_cursor.backends.desktop import DesktopBackend
from ai_cursor.png_grid import read_png_size, write_grid_overlay
from ai_cursor.types import Observation


K_CG_HID_EVENT_TAP = 0
K_CG_EVENT_LEFT_MOUSE_DOWN = 1
K_CG_EVENT_LEFT_MOUSE_UP = 2
K_CG_EVENT_MOUSE_MOVED = 5
K_CG_EVENT_LEFT_MOUSE_DRAGGED = 6
K_CG_MOUSE_BUTTON_LEFT = 0


class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class CGRect(ctypes.Structure):
    _fields_ = [("origin", CGPoint), ("size", CGSize)]


class MacOSDesktopBackend(DesktopBackend):
    def __init__(self) -> None:
        self.app = _application_services()
        self.cf = _core_foundation()
        self._configure_quartz()

    def observe(
        self,
        artifact_dir: Path,
        step: int,
        use_grid: bool = False,
        grid_cell: int = 80,
        target: str = "desktop",
    ) -> Observation:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        raw_path = artifact_dir / f"{step:03d}_screen.png"
        grid_path = artifact_dir / f"{step:03d}_screen_grid.png" if use_grid else None

        completed = subprocess.run(["screencapture", "-x", str(raw_path)], capture_output=True, text=True, timeout=30)
        if completed.returncode != 0:
            raise RuntimeError(
                "macOS screenshot capture failed. Grant Screen Recording permission to the terminal/Python app. "
                + (completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}")
            )

        width, height = read_png_size(raw_path)
        metadata = {
            "left": 0,
            "top": 0,
            "width": width,
            "height": height,
            "screenshot": str(raw_path),
            "grid": str(grid_path) if grid_path else "",
            **self._display_metadata(width, height),
        }

        if grid_path:
            try:
                write_grid_overlay(raw_path, grid_path, grid_cell)
            except Exception as exc:
                shutil.copyfile(raw_path, grid_path)
                metadata["grid_error"] = str(exc)

        return Observation(
            screenshot_path=raw_path,
            grid_path=grid_path,
            width=width,
            height=height,
            left=0,
            top=0,
            target=target,
            step=step,
            metadata=metadata,
        )

    def move(self, x: int, y: int, observation: Observation | None = None) -> None:
        screen_x, screen_y = _to_screen_coords(x, y, observation)
        self._post_mouse(K_CG_EVENT_MOUSE_MOVED, screen_x, screen_y)

    def click(self, x: int, y: int, observation: Observation | None = None) -> None:
        screen_x, screen_y = _to_screen_coords(x, y, observation)
        self._post_mouse(K_CG_EVENT_MOUSE_MOVED, screen_x, screen_y)
        time.sleep(0.05)
        self._post_mouse(K_CG_EVENT_LEFT_MOUSE_DOWN, screen_x, screen_y)
        time.sleep(0.03)
        self._post_mouse(K_CG_EVENT_LEFT_MOUSE_UP, screen_x, screen_y)

    def double_click(self, x: int, y: int, observation: Observation | None = None) -> None:
        self.click(x, y, observation)
        time.sleep(0.08)
        self.click(x, y, observation)

    def drag(
        self,
        x: int,
        y: int,
        to_x: int,
        to_y: int,
        observation: Observation | None = None,
        duration: float = 0.7,
    ) -> None:
        start_x, start_y = _to_screen_coords(x, y, observation)
        end_x, end_y = _to_screen_coords(to_x, to_y, observation)
        duration = max(0.1, min(float(duration), 5.0))
        steps = max(8, int(duration * 60))

        self._post_mouse(K_CG_EVENT_MOUSE_MOVED, start_x, start_y)
        time.sleep(0.08)
        self._post_mouse(K_CG_EVENT_LEFT_MOUSE_DOWN, start_x, start_y)
        try:
            for step in range(1, steps + 1):
                ratio = step / steps
                current_x = start_x + (end_x - start_x) * ratio
                current_y = start_y + (end_y - start_y) * ratio
                self._post_mouse(K_CG_EVENT_LEFT_MOUSE_DRAGGED, current_x, current_y)
                time.sleep(duration / steps)
        finally:
            time.sleep(0.08)
            self._post_mouse(K_CG_EVENT_LEFT_MOUSE_UP, end_x, end_y)

    def type_text(self, text: str) -> None:
        for char in text:
            if char == "\n":
                self.press_key("enter")
            else:
                self._post_unicode_char(char)
            time.sleep(0.01)

    def press_key(self, key: str) -> None:
        tokens = [part.strip().lower() for part in key.split("+") if part.strip()]
        if not tokens:
            raise ValueError("Key cannot be empty")

        keycodes = [_keycode(token) for token in tokens]
        modifiers = keycodes[:-1]
        final = keycodes[-1]
        for keycode in modifiers:
            self._post_key(keycode, True)
            time.sleep(0.01)
        self._post_key(final, True)
        time.sleep(0.03)
        self._post_key(final, False)
        for keycode in reversed(modifiers):
            time.sleep(0.01)
            self._post_key(keycode, False)

    def _configure_quartz(self) -> None:
        self.app.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32]
        self.app.CGEventCreateMouseEvent.restype = ctypes.c_void_p
        self.app.CGEventCreateKeyboardEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_bool]
        self.app.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
        self.app.CGEventKeyboardSetUnicodeString.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_uint16),
        ]
        self.app.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        self.cf.CFRelease.argtypes = [ctypes.c_void_p]

    def _post_mouse(self, event_type: int, x: float, y: float) -> None:
        event = self.app.CGEventCreateMouseEvent(
            None,
            event_type,
            CGPoint(float(x), float(y)),
            K_CG_MOUSE_BUTTON_LEFT,
        )
        if not event:
            raise RuntimeError("CGEventCreateMouseEvent failed")
        try:
            self.app.CGEventPost(K_CG_HID_EVENT_TAP, event)
        finally:
            self.cf.CFRelease(event)

    def _post_key(self, keycode: int, down: bool) -> None:
        event = self.app.CGEventCreateKeyboardEvent(None, ctypes.c_uint16(keycode), bool(down))
        if not event:
            raise RuntimeError("CGEventCreateKeyboardEvent failed")
        try:
            self.app.CGEventPost(K_CG_HID_EVENT_TAP, event)
        finally:
            self.cf.CFRelease(event)

    def _post_unicode_char(self, char: str) -> None:
        units = _utf16_units(char)
        array_type = ctypes.c_uint16 * len(units)
        unit_array = array_type(*units)
        for down in (True, False):
            event = self.app.CGEventCreateKeyboardEvent(None, 0, down)
            if not event:
                raise RuntimeError("CGEventCreateKeyboardEvent failed")
            try:
                self.app.CGEventKeyboardSetUnicodeString(event, len(units), unit_array)
                self.app.CGEventPost(K_CG_HID_EVENT_TAP, event)
            finally:
                self.cf.CFRelease(event)

    def _display_metadata(self, screenshot_width: int, screenshot_height: int) -> dict:
        try:
            self.app.CGMainDisplayID.restype = ctypes.c_uint32
            display = self.app.CGMainDisplayID()
            self.app.CGDisplayPixelsWide.argtypes = [ctypes.c_uint32]
            self.app.CGDisplayPixelsHigh.argtypes = [ctypes.c_uint32]
            self.app.CGDisplayPixelsWide.restype = ctypes.c_size_t
            self.app.CGDisplayPixelsHigh.restype = ctypes.c_size_t
            self.app.CGDisplayBounds.argtypes = [ctypes.c_uint32]
            self.app.CGDisplayBounds.restype = CGRect
            bounds = self.app.CGDisplayBounds(display)
            point_width = bounds.size.width or float(screenshot_width)
            point_height = bounds.size.height or float(screenshot_height)
            pixel_width = float(self.app.CGDisplayPixelsWide(display) or screenshot_width)
            pixel_height = float(self.app.CGDisplayPixelsHigh(display) or screenshot_height)
            return {
                "point_left": bounds.origin.x,
                "point_top": bounds.origin.y,
                "point_width": point_width,
                "point_height": point_height,
                "scale_x": pixel_width / point_width if point_width else 1.0,
                "scale_y": pixel_height / point_height if point_height else 1.0,
            }
        except Exception as exc:
            return {"point_left": 0.0, "point_top": 0.0, "scale_x": 1.0, "scale_y": 1.0, "display_error": str(exc)}


def _application_services() -> ctypes.CDLL:
    return ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")


def _core_foundation() -> ctypes.CDLL:
    return ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")


def _to_screen_coords(x: int, y: int, observation: Observation | None) -> tuple[float, float]:
    if observation is None:
        return float(x), float(y)
    scale_x = float(observation.metadata.get("scale_x", 1.0) or 1.0)
    scale_y = float(observation.metadata.get("scale_y", 1.0) or 1.0)
    point_left = float(observation.metadata.get("point_left", 0.0) or 0.0)
    point_top = float(observation.metadata.get("point_top", 0.0) or 0.0)
    return point_left + (float(x) / scale_x), point_top + (float(y) / scale_y)


def _utf16_units(char: str) -> list[int]:
    encoded = char.encode("utf-16-le")
    return [int.from_bytes(encoded[index : index + 2], "little") for index in range(0, len(encoded), 2)]


def _keycode(token: str) -> int:
    aliases = {
        "cmd": 55,
        "command": 55,
        "win": 55,
        "ctrl": 59,
        "control": 59,
        "shift": 56,
        "alt": 58,
        "option": 58,
        "enter": 36,
        "return": 36,
        "tab": 48,
        "escape": 53,
        "esc": 53,
        "backspace": 51,
        "delete": 51,
        "del": 51,
        "forward_delete": 117,
        "space": 49,
        "left": 123,
        "right": 124,
        "down": 125,
        "up": 126,
        "home": 115,
        "end": 119,
        "pageup": 116,
        "pagedown": 121,
    }
    if token in aliases:
        return aliases[token]

    letter_codes = {
        "a": 0,
        "s": 1,
        "d": 2,
        "f": 3,
        "h": 4,
        "g": 5,
        "z": 6,
        "x": 7,
        "c": 8,
        "v": 9,
        "b": 11,
        "q": 12,
        "w": 13,
        "e": 14,
        "r": 15,
        "y": 16,
        "t": 17,
        "o": 31,
        "u": 32,
        "i": 34,
        "p": 35,
        "l": 37,
        "j": 38,
        "k": 40,
        "n": 45,
        "m": 46,
    }
    if token in letter_codes:
        return letter_codes[token]

    number_codes = {"1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "9": 25, "7": 26, "8": 28, "0": 29}
    if token in number_codes:
        return number_codes[token]

    punctuation_codes = {"=": 24, "-": 27, "]": 30, "[": 33, "'": 39, ";": 41, "\\": 42, ",": 43, "/": 44, ".": 47, "`": 50}
    if token in punctuation_codes:
        return punctuation_codes[token]

    if token.startswith("f") and token[1:].isdigit():
        function_codes = {
            1: 122,
            2: 120,
            3: 99,
            4: 118,
            5: 96,
            6: 97,
            7: 98,
            8: 100,
            9: 101,
            10: 109,
            11: 103,
            12: 111,
        }
        number = int(token[1:])
        if number in function_codes:
            return function_codes[number]

    raise ValueError(f"Unsupported macOS key token: {token}")
