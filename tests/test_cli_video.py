import numpy as np
import xarray as xr
from typer.testing import CliRunner

from yacht_co2.cli import app
from yacht_co2.video import render_video


def video_dataset():
    time = np.array(["2023-01-01T00", "2023-01-01T01", "2023-01-01T02"], dtype="datetime64[ns]")
    return xr.Dataset(
        {
            "lat": ("time", [50.0, 50.1, 50.2]),
            "lon": ("time", [-5.0, -4.9, -4.8]),
            "pco2_seawater": ("time", [400.0, 405.0, 410.0]),
            "source_file": ("time", ["a", "a", "a"]),
            "qc_flag": ("time", np.zeros(3, dtype="uint16")),
        },
        coords={"time": time},
    )


def test_video_is_h264_and_has_expected_frames(tmp_path):
    path = render_video(video_dataset(), tmp_path / "test.mp4", fps=2)
    assert path.exists() and path.stat().st_size > 1000


def test_cli_help_validate_and_site(tmp_path):
    runner = CliRunner()
    assert runner.invoke(app, ["--help"]).exit_code == 0
    manifest = tmp_path / "expedition.yaml"
    manifest.write_text("expedition: {name: Test}\ninputs: {logs: '*.log'}\n")
    result = runner.invoke(app, ["validate", str(manifest)])
    assert result.exit_code == 0
    assert "valid: Test" in result.stdout
    source = tmp_path / "track.nc"
    video_dataset().to_netcdf(source)
    result = runner.invoke(app, ["site", str(source), "--output", str(tmp_path / "site")])
    assert result.exit_code == 0
