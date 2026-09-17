"""Synchronized map and time-series video rendering."""

from __future__ import annotations

import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from loguru import logger
from matplotlib.animation import FFMpegWriter

from .errors import YachtCO2Error


def ffmpeg_executable() -> str:
    """Return the encoder this machine can actually run.

    Matplotlib looks for an ``ffmpeg`` on the path and says nothing useful when
    there is none. The ``video`` extra installs ``imageio-ffmpeg``, which ships
    a binary of its own precisely so that nobody has to install one by hand, so
    that binary is used whenever the path has nothing -- which is what makes
    ``pip install yacht-co2[video]`` enough on a machine with no system ffmpeg.
    """
    configured = str(plt.rcParams.get("animation.ffmpeg_path") or "ffmpeg")
    if Path(configured).is_file() or shutil.which(configured):
        return configured
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
    except ImportError:
        raise YachtCO2Error(
            "Rendering a video needs ffmpeg, and this machine has none. Install the extra "
            "that brings its own -- pip install 'yacht-co2[video]' -- or put an ffmpeg on "
            "the PATH."
        ) from None
    return get_ffmpeg_exe()


def render_video(
    ds: xr.Dataset,
    destination: str | Path,
    *,
    variable: str = "pco2_seawater",
    frame_interval: str = "1h",
    fps: int = 12,
    dpi: int = 120,
) -> Path:
    """Render a synchronized H.264 track and time-series MP4."""
    if variable not in ds:
        raise KeyError(variable)
    # Asked for before a frame is drawn: an encoder that is not there should
    # say so in one line, not after the figure has been built.
    encoder = ffmpeg_executable()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    valid_time = pd.DatetimeIndex(ds.time.values).dropna()
    frames = pd.date_range(valid_time.min(), valid_time.max(), freq=frame_interval)
    indices = valid_time.get_indexer(frames, method="nearest")
    lon, lat, values = ds.lon.values, ds.lat.values, ds[variable].values
    fig, (map_ax, series_ax) = plt.subplots(1, 2, figsize=(10, 4))
    map_ax.plot(lon, lat, color="0.75", lw=1)
    map_ax.set(xlabel="Longitude", ylabel="Latitude", title="Campaign track")
    point = map_ax.scatter([], [], c="#e6533d", s=35, zorder=3)
    series_ax.plot(ds.time.values, values, color="#087e8b", lw=0.8)
    series_ax.set(xlabel="UTC time", ylabel=variable, title="Time series")
    cursor = series_ax.axvline(ds.time.values[0], color="#e6533d")
    stamp = fig.suptitle("")
    writer = FFMpegWriter(fps=fps, codec="libx264", extra_args=["-pix_fmt", "yuv420p"])
    # The writer reads the encoder's location out of the global settings, so it
    # is put there for the length of this render and no longer: rendering a
    # video should not change how the rest of the process draws.
    with (
        plt.rc_context({"animation.ffmpeg_path": encoder}),
        writer.saving(fig, str(destination), dpi=dpi),
    ):
        for frame, index in zip(frames, indices, strict=True):
            point.set_offsets(np.array([[lon[index], lat[index]]]))
            cursor.set_xdata([ds.time.values[index], ds.time.values[index]])
            stamp.set_text(frame.strftime("%Y-%m-%d %H:%M UTC"))
            writer.grab_frame()
    plt.close(fig)
    logger.success("Rendered {} frames to {}", len(frames), destination)
    return destination
