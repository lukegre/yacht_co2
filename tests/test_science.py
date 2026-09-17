import numpy as np
import pytest
import xarray as xr

from yacht_co2.qc import apply_qc
from yacht_co2.schema import QCFlag
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


def test_linear_calibration_and_a_non_seawater_phase_passes_qc():
    """A record outside the analysis phases is not seawater, and not bad data."""
    ds = calibrate_co2(
        dataset(),
        {"method": "linear", "zero_measured": 10, "span_measured": 510, "span_certified": 500},
    )
    assert ds.xco2_wet[0] == pytest.approx(390)
    checked = apply_qc(ds, {}, {"analysis": [5]})

    assert int(checked.qc_flag[0]) == 0
    assert int(checked.qc_flag[1]) == 0
    # The phase is carried as a selector rather than as a quality judgement.
    assert checked.seawater.values.tolist() == [True, False]


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
        {"method": "linear", "standards": {"span": 500}},
        {"zero": [2]},
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


def calibration_track():
    """Four records: two on seawater, a zero and a span."""
    return xr.Dataset(
        {
            "lat": ("time", np.full(4, 50.0)),
            "lon": ("time", np.full(4, -5.0)),
            "source_file": ("time", ["a"] * 4),
            "qc_flag": ("time", np.zeros(4, dtype="uint16")),
            # The zero reads near nothing and the span above the seawater
            # range, which is what a zero and a span are supposed to do.
            "raw_co2": ("time", [400.0, 410.0, 0.5, 1500.0]),
            "raw_watertemp": ("time", np.full(4, 20.0)),
            "raw_salinity": ("time", np.full(4, 35.0)),
            "raw_waterflow": ("time", [2.0, 2.0, 0.0, 0.0]),
            "raw_sampling_phase": ("time", [5.0, 5.0, 2.0, 1.0]),
        },
        coords={
            "time": np.array(
                ["2023-01-01T00", "2023-01-01T01", "2023-01-01T02", "2023-01-01T03"],
                dtype="datetime64[ns]",
            )
        },
    )


def test_seawater_checks_are_not_asked_of_the_gas_standards():
    """A zero reading 0.5 ppm is doing its job, not failing a seawater range."""
    checked = apply_qc(calibration_track(), {"minimum_water_flow": 0.1}, {"analysis": [5]})

    assert checked.qc_flag.values.tolist() == [0, 0, 0, 0]
    assert checked.qc_good.values.tolist() == [True] * 4
    assert checked.seawater.values.tolist() == [True, True, False, False]


def test_seawater_records_are_still_checked():
    """Scoping the checks to seawater must not stop them catching bad seawater."""
    ds = calibration_track()
    values = ds.raw_co2.values.copy()
    values[1] = 5000.0  # a real seawater record, far outside the range
    ds["raw_co2"] = ("time", values)

    checked = apply_qc(ds, {"minimum_water_flow": 0.1}, {"analysis": [5]})

    assert int(checked.qc_flag[1]) & int(QCFlag.PHYSICAL_RANGE)
    assert checked.qc_good.values.tolist() == [True, False, True, True]


def test_the_phase_bit_is_no_longer_set():
    """The phase is a selector now; nothing is flagged for being a gas standard."""
    checked = apply_qc(calibration_track(), {}, {"analysis": [5]})

    assert not (checked.qc_flag.values & int(QCFlag.EXCLUDED_PHASE)).any()


def test_a_track_without_a_phase_column_is_all_seawater():
    ds = calibration_track().drop_vars("raw_sampling_phase")

    checked = apply_qc(ds, {}, {"analysis": [5]})

    assert checked.seawater.values.all()
    # With no phase to scope by, the seawater ranges apply to every record.
    assert int(checked.qc_flag[2]) & int(QCFlag.PHYSICAL_RANGE)


def transition_track(minutes=1.0):
    """A seawater stretch, then a zero, then seawater again."""
    phases = [5.0] * 4 + [2.0] * 4 + [5.0] * 4
    count = len(phases)
    return xr.Dataset(
        {
            "lat": ("time", np.full(count, 50.0)),
            "lon": ("time", np.full(count, -5.0)),
            "source_file": ("time", ["a"] * count),
            "qc_flag": ("time", np.zeros(count, dtype="uint16")),
            "raw_co2": ("time", np.where(np.array(phases) == 5.0, 400.0, 0.5)),
            "raw_sampling_phase": ("time", phases),
        },
        coords={
            "time": np.datetime64("2023-01-01T00:00", "ns")
            + (np.arange(count) * minutes * 60 * 1e9).astype("timedelta64[ns]")
        },
    )


def test_each_phase_settles_at_its_own_rate():
    """The lag is counted from each phase transition, per phase."""
    config = {"phase_transition_lag": {"analysis": 120, "zero": 180}}

    checked = apply_qc(transition_track(), config, {"analysis": [5], "zero": [2]})

    lagged = (checked.qc_flag.values & int(QCFlag.TRANSITION_LAG)).astype(bool)
    # Two minutes of seawater, three of zero, then two of seawater again.
    assert lagged.tolist() == [
        True, True, False, False,
        True, True, True, False,
        True, True, False, False,
    ]  # fmt: skip
    assert not checked.qc_good.values[0]


def test_a_phase_without_a_lag_is_not_flagged():
    checked = apply_qc(
        transition_track(), {"phase_transition_lag": {"zero": 180}}, {"analysis": [5], "zero": [2]}
    )

    lagged = (checked.qc_flag.values & int(QCFlag.TRANSITION_LAG)).astype(bool)
    assert lagged.tolist() == [False] * 4 + [True, True, True, False] + [False] * 4


def test_a_lag_naming_an_undescribed_phase_is_an_error():
    with pytest.raises(ValueError, match="analyis"):
        apply_qc(transition_track(), {"phase_transition_lag": {"analyis": 120}}, {"analysis": [5]})


def test_a_lag_needs_a_number_of_seconds():
    with pytest.raises(ValueError, match="seconds"):
        apply_qc(
            transition_track(), {"phase_transition_lag": {"analysis": "2min"}}, {"analysis": [5]}
        )


def test_no_lag_leaves_every_record_unflagged():
    checked = apply_qc(transition_track(), {}, {"analysis": [5]})

    assert not (checked.qc_flag.values & int(QCFlag.TRANSITION_LAG)).any()
