from __future__ import annotations

import base64
import ctypes
import json
import shutil
import subprocess
import time
from pathlib import Path

from ai_cursor.backends.desktop import DesktopBackend
from ai_cursor.types import Observation


MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004


class WindowsDesktopBackend(DesktopBackend):
    def __init__(self) -> None:
        self.user32 = ctypes.windll.user32
        _make_dpi_aware()

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
        metadata = _capture_screen(raw_path, grid_path, grid_cell)
        return Observation(
            screenshot_path=raw_path,
            grid_path=grid_path,
            width=int(metadata["width"]),
            height=int(metadata["height"]),
            left=int(metadata.get("left", 0)),
            top=int(metadata.get("top", 0)),
            target=target,
            step=step,
            metadata=metadata,
        )

    def move(self, x: int, y: int, observation: Observation | None = None) -> None:
        sx, sy = _to_screen_coords(x, y, observation)
        if not self.user32.SetCursorPos(int(sx), int(sy)):
            raise RuntimeError(f"SetCursorPos failed for {sx}, {sy}")

    def click(self, x: int, y: int, observation: Observation | None = None) -> None:
        self.move(x, y, observation)
        time.sleep(0.05)
        self.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.03)
        self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

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

        if not self.user32.SetCursorPos(start_x, start_y):
            raise RuntimeError(f"SetCursorPos failed for {start_x}, {start_y}")
        time.sleep(0.08)
        self.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        try:
            for step in range(1, steps + 1):
                ratio = step / steps
                current_x = round(start_x + (end_x - start_x) * ratio)
                current_y = round(start_y + (end_y - start_y) * ratio)
                if not self.user32.SetCursorPos(current_x, current_y):
                    raise RuntimeError(f"SetCursorPos failed for {current_x}, {current_y}")
                time.sleep(duration / steps)
        finally:
            time.sleep(0.08)
            self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def type_text(self, text: str) -> None:
        for char in text:
            if char == "\n":
                self.press_key("enter")
            else:
                _send_unicode_char(char)
            time.sleep(0.01)

    def press_key(self, key: str) -> None:
        tokens = [part.strip().lower() for part in key.split("+") if part.strip()]
        if not tokens:
            raise ValueError("Key cannot be empty")

        vks = [_virtual_key(token) for token in tokens]
        modifiers = vks[:-1]
        final = vks[-1]
        for vk in modifiers:
            self.user32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.01)
        self.user32.keybd_event(final, 0, 0, 0)
        time.sleep(0.03)
        self.user32.keybd_event(final, 0, KEYEVENTF_KEYUP, 0)
        for vk in reversed(modifiers):
            time.sleep(0.01)
            self.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _capture_screen(raw_path: Path, grid_path: Path | None, grid_cell: int) -> dict:
    executable = shutil.which("powershell") or shutil.which("pwsh")
    if not executable:
        raise RuntimeError("PowerShell is required for Windows screenshot capture")

    script = _screenshot_script(raw_path, grid_path, max(20, int(grid_cell)))
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    args = [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded]
    completed = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if completed.returncode != 0:
        raise RuntimeError(
            "Screenshot capture failed: "
            + (completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}")
        )
    output = completed.stdout.strip()
    try:
        return json.loads(output.splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not parse screenshot metadata: {output}") from exc


def _screenshot_script(raw_path: Path, grid_path: Path | None, grid_cell: int) -> str:
    grid = str(grid_path) if grid_path else ""
    return f"""
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class DpiAware {{
  [DllImport("user32.dll")]
  public static extern bool SetProcessDPIAware();
}}
"@
[DpiAware]::SetProcessDPIAware() | Out-Null
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$rawPath = {_ps_string(str(raw_path))}
$gridPath = {_ps_string(grid)}
$cell = {int(grid_cell)}
$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bitmap = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($bounds.Left, $bounds.Top, 0, 0, $bounds.Size)
$bitmap.Save($rawPath, [System.Drawing.Imaging.ImageFormat]::Png)
if ($gridPath -ne '') {{
  $minorPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(80, 0, 210, 255), 1)
  $majorPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(180, 255, 255, 255), 1)
  $font = New-Object System.Drawing.Font('Consolas', 9)
  $labelBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(235, 255, 255, 255))
  $backBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(155, 0, 0, 0))
  $major = $cell * 5
  for ($x = 0; $x -lt $bounds.Width; $x += $cell) {{
    if (($x % $major) -eq 0) {{ $pen = $majorPen }} else {{ $pen = $minorPen }}
    $graphics.DrawLine($pen, $x, 0, $x, $bounds.Height)
    if (($x % $major) -eq 0) {{
      $graphics.FillRectangle($backBrush, $x + 2, 2, 54, 16)
      $graphics.DrawString([string]$x, $font, $labelBrush, $x + 4, 3)
    }}
  }}
  for ($y = 0; $y -lt $bounds.Height; $y += $cell) {{
    if (($y % $major) -eq 0) {{ $pen = $majorPen }} else {{ $pen = $minorPen }}
    $graphics.DrawLine($pen, 0, $y, $bounds.Width, $y)
    if (($y % $major) -eq 0) {{
      $graphics.FillRectangle($backBrush, 2, $y + 2, 54, 16)
      $graphics.DrawString([string]$y, $font, $labelBrush, 4, $y + 3)
    }}
  }}
  $bitmap.Save($gridPath, [System.Drawing.Imaging.ImageFormat]::Png)
  $minorPen.Dispose(); $majorPen.Dispose(); $font.Dispose(); $labelBrush.Dispose(); $backBrush.Dispose()
}}
$graphics.Dispose()
$bitmap.Dispose()
$result = [ordered]@{{
  left = [int]$bounds.Left
  top = [int]$bounds.Top
  width = [int]$bounds.Width
  height = [int]$bounds.Height
  screenshot = $rawPath
  grid = $gridPath
}}
$result | ConvertTo-Json -Compress
"""


def _ps_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _to_screen_coords(x: int, y: int, observation: Observation | None) -> tuple[int, int]:
    if observation is None:
        return int(x), int(y)
    return int(x + observation.left), int(y + observation.top)


def _make_dpi_aware() -> None:
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _send_unicode_char(char: str) -> None:
    code = ord(char)

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("union", INPUT_UNION)]

    extra = ctypes.c_ulong(0)
    down = INPUT(type=1, union=INPUT_UNION(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, ctypes.pointer(extra))))
    up = INPUT(
        type=1,
        union=INPUT_UNION(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, ctypes.pointer(extra))),
    )
    ctypes.windll.user32.SendInput(1, ctypes.pointer(down), ctypes.sizeof(INPUT))
    ctypes.windll.user32.SendInput(1, ctypes.pointer(up), ctypes.sizeof(INPUT))


def _virtual_key(token: str) -> int:
    aliases = {
        "ctrl": 0x11,
        "control": 0x11,
        "shift": 0x10,
        "alt": 0x12,
        "win": 0x5B,
        "cmd": 0x5B,
        "enter": 0x0D,
        "return": 0x0D,
        "tab": 0x09,
        "escape": 0x1B,
        "esc": 0x1B,
        "backspace": 0x08,
        "space": 0x20,
        "delete": 0x2E,
        "del": 0x2E,
        "home": 0x24,
        "end": 0x23,
        "pageup": 0x21,
        "pagedown": 0x22,
        "left": 0x25,
        "up": 0x26,
        "right": 0x27,
        "down": 0x28,
    }
    if token in aliases:
        return aliases[token]
    if len(token) == 1:
        return ord(token.upper())
    if token.startswith("f") and token[1:].isdigit():
        number = int(token[1:])
        if 1 <= number <= 24:
            return 0x70 + number - 1
    raise ValueError(f"Unsupported key token: {token}")
