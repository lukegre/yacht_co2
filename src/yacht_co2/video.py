"""Synchronized map and time-series video rendering."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from loguru import logger
from matplotlib.animation import FFMpegWriter


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
    with writer.saving(fig, str(destination), dpi=dpi):
        for frame, index in zip(frames, indices, strict=True):
            point.set_offsets(np.array([[lon[index], lat[index]]]))
            cursor.set_xdata([ds.time.values[index], ds.time.values[index]])
            stamp.set_text(frame.strftime("%Y-%m-%d %H:%M UTC"))
            writer.grab_frame()
    plt.close(fig)
    logger.success("Rendered {} frames to {}", len(frames), destination)
    return destination
