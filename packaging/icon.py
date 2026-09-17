"""The application's icon, drawn rather than stored.

A packaged application wants a real icon -- an ``.icns`` on macOS, an ``.ico``
on Windows -- and keeping a pile of rendered sizes in the repository means
keeping them in step with nothing. The mark is simple enough to describe: the
masthead navy of the campaign site, the sea it sits over and one sensor reading
crossing it, so it is described here and rendered at build time in whatever
sizes the platform asks for.

Run it directly to look at the result::

    uv run python packaging/icon.py build/icons
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

#: Taken from the campaign site's own palette, so the application and the pages
#: it produces are recognisably the same thing.
NAVY = (7, 59, 76, 255)
SEA = (8, 126, 139, 255)
FOAM = (228, 241, 244, 255)
ACCENT = (230, 83, 61, 255)

#: Windows reads every size it needs out of one file; these are the ones it
#: asks for, from the taskbar up to the largest tile.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

#: Everything is drawn at this many times the size it is wanted and then scaled
#: down, which is how the curve and the rounded corners get their smooth edges:
#: Pillow's drawing primitives do not antialias, and its resampling does.
SUPERSAMPLE = 4

#: The size the mark is composed at, before any of it is scaled down.
CANVAS = 1024


def _stroke(
    canvas: ImageDraw.ImageDraw,
    points: list[tuple[float, float]],
    *,
    colour: tuple[int, int, int, int],
    width: float,
) -> None:
    """Draw a smooth line of a given thickness through ``points``.

    Pillow's own ``joint="curve"`` fills the outside of each corner with a small
    arc, and at this line width that leaves a row of notches along the whole
    curve. Stamping a disc at every point instead gives round joins and round
    ends for free, and there are few enough points for it to cost nothing.
    """
    canvas.line(points, fill=colour, width=max(1, round(width)))
    radius = width / 2
    for x, y in points:
        canvas.ellipse((x - radius, y - radius, x + radius, y + radius), fill=colour)


def _compose(size: int) -> Image.Image:
    """Draw the mark, hard-edged, at one size."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas = ImageDraw.Draw(image)
    unit = size / CANVAS

    # A rounded tile rather than a bare circle: at 16 pixels a square reads as
    # an application and a circle reads as a smudge.
    inset, radius = 32 * unit, 210 * unit
    tile = (inset, inset, size - inset, size - inset)
    canvas.rounded_rectangle(tile, radius=radius, fill=NAVY)

    # The sea is a band along the bottom, low enough to leave the trace above
    # it a clear field, with a flat top -- a wave there as well would be one
    # wiggle more than survives being made small. Asking rounded_rectangle for
    # the tile's own corner radius on a band this shallow overflows its
    # bounding box and leaves square notches poking out past the curve, so
    # the band is painted through a mask cut from the tile's own shape
    # instead: its bottom corners then follow the tile exactly, whatever the
    # band's height.
    horizon = inset + (size - 2 * inset) * 0.70
    sea_mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(sea_mask).rounded_rectangle(tile, radius=radius, fill=255)
    ImageDraw.Draw(sea_mask).rectangle((0, 0, size, horizon), fill=0)
    image.paste(Image.new("RGBA", (size, size), SEA), mask=sea_mask)

    # One trace across the navy: the reading the whole package exists to make.
    left, right = inset + 105 * unit, size - inset - 105 * unit
    amplitude = 88 * unit
    centre = inset + (horizon - inset) * 0.52
    span = right - left
    trace = [
        (
            left + step * span / 240,
            centre - amplitude * math.sin(step / 240 * 2.1 * math.pi + 0.35),
        )
        for step in range(241)
    ]
    _stroke(canvas, trace, colour=FOAM, width=52 * unit)

    # And the last point of it, marked, because a track is read from its end.
    x, y = trace[-1]
    dot = 62 * unit
    canvas.ellipse((x - dot, y - dot, x + dot, y + dot), fill=ACCENT)
    return image


def draw(size: int = CANVAS) -> Image.Image:
    """Draw the mark at one size, antialiased, on transparency."""
    return _compose(size * SUPERSAMPLE).resize((size, size), Image.LANCZOS)


def write_png(destination: Path, size: int = CANVAS) -> Path:
    """Write the mark as a single PNG."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    draw(size).save(destination)
    return destination


def write_ico(destination: Path) -> Path:
    """Write the Windows icon, with every size it asks for inside it."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    draw(CANVAS).save(destination, format="ICO", sizes=[(n, n) for n in ICO_SIZES])
    return destination


def write_icns(destination: Path) -> Path:
    """Write the macOS icon.

    Pillow builds the whole container -- every size macOS asks for, including
    the Retina ones -- from the single 1024-pixel master, which means a macOS
    icon can be produced on any machine. ``iconutil`` would be the obvious
    alternative, but it exists only on macOS and needs a directory of files
    named exactly as it expects, and this needs neither.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    draw(CANVAS).save(destination, format="ICNS")
    return destination


def build(directory: Path) -> dict[str, Path]:
    """Write every icon this platform can use, and say where each went."""
    return {
        "png": write_png(directory / "yacht-co2.png"),
        "ico": write_ico(directory / "yacht-co2.ico"),
        "icns": write_icns(directory / "yacht-co2.icns"),
    }


def platform_icon(directory: Path) -> Path | None:
    """Return the icon PyInstaller should embed on this platform."""
    written = build(directory)
    if sys.platform == "darwin":
        return written.get("icns")
    if sys.platform == "win32":
        return written.get("ico")
    # Linux takes its icon from a .desktop entry, not from the executable.
    return written.get("png")


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "build/icons")
    for kind, path in build(target).items():
        print(f"{kind}: {path}")
