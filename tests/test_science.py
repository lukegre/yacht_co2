import numpy as np
import pytest
import xarray as xr

from yacht_co2.qc import apply_qc
from yacht_co2.science import (
    calibrate_co2,
    derive_fco2,
    derive_flux,
    derive_pco2,
    fugacity_factor,
    schmidt_number_co2,
    solubility_co2,
)


def dataset():
    return xr.Dataset(
        {
            "lat": ("time", [50.0, 50.0]),
            "lon": ("time", [-5.0, -5.0]),
            "source_file": ("time", ["a", "a"]),
            "qc_flag": ("time", np.zeros(2, dtype="uint16")),
            "raw_co2": ("time", [400.0, 410.0]),
            "raw_h2o": ("time", [10.0, 10.0]),
            "raw_celltemp": ("time", [51.5, 51.5]),
            "raw_equilibrator_water_temp": ("time", [20.0, 21.0]),
            "raw_cellpress": ("time", [1013.25, 1013.25]),
            "raw_watertemp": ("time", [20.0, 22.0]),
            "raw_salinity": ("time", [35.0, 35.0]),
            "raw_sampling_phase": ("time", [5.0, 19.0]),
            "raw_flowgas": ("time", [1.0, 1.0]),
            "raw_waterflow": ("time", [1.0, 1.0]),
        },
        coords={"time": np.array(["2023-01-01", "2023-01-02"], dtype="datetime64[ns]")},
    )


def test_processing_algebra_and_unity_temperature_correction():
    ds = derive_pco2(calibrate_co2(dataset()))
    assert ds.xco2_dry[0] == pytest.approx(400 / 0.99, rel=1e-12)
    # drying and dry pressure cancel when cell pressure is standard pressure
    assert ds.pco2_seawater[0] == pytest.approx(400, rel=1e-12)
    assert ds.pco2_seawater[1] == pytest.approx(410, rel=1e-12)
    assert fugacity_factor(20) == pytest.approx(0.9966526904398437, rel=1e-12)


def test_temperature_correction_uses_equilibrator_water_temperature():
    ds = derive_pco2(
        calibrate_co2(dataset()),
        {"water_temperature": "equilibrator_water_temp"},
    )
    assert ds.pco2_seawater[0] == pytest.approx(400, rel=1e-12)
    assert ds.pco2_seawater[1] == pytest.approx(410 * np.exp(0.0423), rel=1e-12)


def test_linear_calibration_and_qc_bits():
    ds = calibrate_co2(
        dataset(),
        {"method": "linear", "zero_measured": 10, "span_measured": 510, "span_certified": 500},
    )
    assert ds.xco2_wet[0] == pytest.approx(390)
    checked = apply_qc(ds, {"analysis_phases": [5]})
    assert int(checked.qc_flag[0]) == 0
    assert int(checked.qc_flag[1]) & 8


def test_phase_derived_linear_calibration():
    base = dataset().isel(time=[0, 0, 0, 0]).copy()
    base["raw_co2"] = ("time", [10.0, 510.0, 260.0, 520.0])
    base["raw_sampling_phase"] = ("time", [2.0, 1.0, 5.0, 1.0])
    base["time"] = np.array(
        ["2023-01-01T00", "2023-01-01T01", "2023-01-01T02", "2023-01-01T03"],
        dtype="datetime64[ns]",
    )
    calibrated = calibrate_co2(
        base,
        {"method": "linear", "standards": {"span": 500}, "zero_phase": 2},
    )
    assert np.isfinite(calibrated.xco2_wet).all()
    assert calibrated.xco2_wet[0] == pytest.approx(0)


def test_flux_zero_gradient_sign_and_missing():
    ds = derive_fco2(derive_pco2(calibrate_co2(dataset())))
    ds["wind_speed"] = ("time", [10.0, np.nan])
    ds["fco2_air"] = ds.fco2_seawater.copy()
    zero = derive_flux(ds)
    assert zero.co2_flux[0] == pytest.approx(0, abs=1e-14)
    assert np.isnan(zero.co2_flux[1])
    ds["fco2_air"] = ds.fco2_seawater - 10
    assert derive_flux(ds).co2_flux[0] > 0
    assert schmidt_number_co2(20) == pytest.approx(668.344)
    assert solubility_co2(20, 35) == pytest.approx(33.215, rel=1e-3)
