from __future__ import annotations

import struct
import zlib
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


DIGITS = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "-": ("000", "000", "111", "000", "000"),
}


def read_png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        if handle.read(8) != PNG_SIGNATURE:
            raise ValueError(f"{path} is not a PNG file")
        length = struct.unpack(">I", handle.read(4))[0]
        chunk_type = handle.read(4)
        if chunk_type != b"IHDR" or length != 13:
            raise ValueError(f"{path} does not start with an IHDR chunk")
        data = handle.read(length)
        width, height = struct.unpack(">II", data[:8])
        return width, height


def write_grid_overlay(source_path: Path, output_path: Path, cell_size: int = 80) -> None:
    png = _read_png(source_path)
    _draw_grid(png["rows"], png["width"], png["height"], png["bpp"], max(20, int(cell_size)))
    _write_png(output_path, png)


def _read_png(path: Path) -> dict:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError(f"{path} is not a PNG file")

    offset = len(PNG_SIGNATURE)
    ihdr = None
    idat_parts: list[bytes] = []

    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        offset += 12 + length

        if chunk_type == b"IHDR":
            ihdr = chunk_data
        elif chunk_type == b"IDAT":
            idat_parts.append(chunk_data)
        elif chunk_type == b"IEND":
            break

    if ihdr is None:
        raise ValueError(f"{path} is missing IHDR")

    width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(">IIBBBBB", ihdr)
    if bit_depth != 8 or color_type not in {2, 6} or compression != 0 or filter_method != 0 or interlace != 0:
        raise ValueError("Grid overlay supports non-interlaced 8-bit RGB/RGBA PNG screenshots only")

    bpp = 4 if color_type == 6 else 3
    rows = _unfilter_scanlines(zlib.decompress(b"".join(idat_parts)), width, height, bpp)
    return {
        "width": width,
        "height": height,
        "bit_depth": bit_depth,
        "color_type": color_type,
        "compression": compression,
        "filter_method": filter_method,
        "interlace": interlace,
        "bpp": bpp,
        "rows": rows,
    }


def _unfilter_scanlines(raw: bytes, width: int, height: int, bpp: int) -> list[bytearray]:
    stride = width * bpp
    rows: list[bytearray] = []
    offset = 0
    previous = bytearray(stride)

    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        row = bytearray(raw[offset : offset + stride])
        offset += stride

        for index in range(stride):
            left = row[index - bpp] if index >= bpp else 0
            up = previous[index]
            up_left = previous[index - bpp] if index >= bpp else 0

            if filter_type == 1:
                row[index] = (row[index] + left) & 0xFF
            elif filter_type == 2:
                row[index] = (row[index] + up) & 0xFF
            elif filter_type == 3:
                row[index] = (row[index] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                row[index] = (row[index] + _paeth(left, up, up_left)) & 0xFF
            elif filter_type != 0:
                raise ValueError(f"Unsupported PNG filter type {filter_type}")

        rows.append(row)
        previous = row

    return rows


def _draw_grid(rows: list[bytearray], width: int, height: int, bpp: int, cell: int) -> None:
    major = cell * 5
    for x in range(0, width, cell):
        color = (255, 255, 255, 255) if x % major == 0 else (0, 210, 255, 255)
        _draw_vertical(rows, width, height, bpp, x, color)
    for y in range(0, height, cell):
        color = (255, 255, 255, 255) if y % major == 0 else (0, 210, 255, 255)
        _draw_horizontal(rows, width, height, bpp, y, color)

    for x in range(0, width, major):
        _draw_label(rows, width, height, bpp, str(x), x + 4, 4)
    for y in range(0, height, major):
        _draw_label(rows, width, height, bpp, str(y), 4, y + 4)


def _draw_vertical(rows: list[bytearray], width: int, height: int, bpp: int, x: int, color: tuple[int, int, int, int]) -> None:
    if not 0 <= x < width:
        return
    for y in range(height):
        _set_pixel(rows, x, y, bpp, color)


def _draw_horizontal(rows: list[bytearray], width: int, height: int, bpp: int, y: int, color: tuple[int, int, int, int]) -> None:
    if not 0 <= y < height:
        return
    for x in range(width):
        _set_pixel(rows, x, y, bpp, color)


def _draw_label(rows: list[bytearray], width: int, height: int, bpp: int, text: str, x: int, y: int) -> None:
    scale = 2
    char_width = 3 * scale
    char_height = 5 * scale
    label_width = max(1, len(text)) * (char_width + scale) + scale
    label_height = char_height + scale * 2
    _draw_rect(rows, width, height, bpp, x - 2, y - 2, label_width + 4, label_height, (0, 0, 0, 255))

    cursor = x
    for char in text:
        _draw_char(rows, width, height, bpp, char, cursor, y, scale)
        cursor += char_width + scale


def _draw_char(rows: list[bytearray], width: int, height: int, bpp: int, char: str, x: int, y: int, scale: int) -> None:
    glyph = DIGITS.get(char)
    if not glyph:
        return
    for row_index, pattern in enumerate(glyph):
        for col_index, bit in enumerate(pattern):
            if bit != "1":
                continue
            _draw_rect(
                rows,
                width,
                height,
                bpp,
                x + col_index * scale,
                y + row_index * scale,
                scale,
                scale,
                (255, 255, 255, 255),
            )


def _draw_rect(
    rows: list[bytearray],
    width: int,
    height: int,
    bpp: int,
    x: int,
    y: int,
    rect_width: int,
    rect_height: int,
    color: tuple[int, int, int, int],
) -> None:
    for yy in range(max(0, y), min(height, y + rect_height)):
        for xx in range(max(0, x), min(width, x + rect_width)):
            _set_pixel(rows, xx, yy, bpp, color)


def _set_pixel(rows: list[bytearray], x: int, y: int, bpp: int, color: tuple[int, int, int, int]) -> None:
    offset = x * bpp
    rows[y][offset] = color[0]
    rows[y][offset + 1] = color[1]
    rows[y][offset + 2] = color[2]
    if bpp == 4:
        rows[y][offset + 3] = color[3]


def _write_png(path: Path, png: dict) -> None:
    raw = bytearray()
    for row in png["rows"]:
        raw.append(0)
        raw.extend(row)

    ihdr = struct.pack(
        ">IIBBBBB",
        png["width"],
        png["height"],
        png["bit_depth"],
        png["color_type"],
        png["compression"],
        png["filter_method"],
        png["interlace"],
    )
    output = bytearray(PNG_SIGNATURE)
    output.extend(_chunk(b"IHDR", ihdr))
    output.extend(_chunk(b"IDAT", zlib.compress(bytes(raw), level=6)))
    output.extend(_chunk(b"IEND", b""))
    path.write_bytes(bytes(output))


def _chunk(chunk_type: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(chunk_type)
    checksum = zlib.crc32(data, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", checksum)


def _paeth(left: int, up: int, up_left: int) -> int:
    p = left + up - up_left
    pa = abs(p - left)
    pb = abs(p - up)
    pc = abs(p - up_left)
    if pa <= pb and pa <= pc:
        return left
    if pb <= pc:
        return up
    return up_left
