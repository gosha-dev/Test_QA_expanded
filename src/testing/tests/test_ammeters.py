"""Configuration-driven integration tests for simulator-backed ammeters."""

import math
import os
import sys
import subprocess
import time


import pytest


from src.testing.test_framework import AmmeterTestFramework, AmmeterSampling, create_config_with_overrides
from src.testing.result_manager import SampleResult


@pytest.fixture(scope="module", autouse=True)
def run_ammeter_simulation(project_root):
    process = subprocess.Popen(
        [sys.executable, str(project_root / "main.py")],
        cwd=project_root,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    try:
        time.sleep(5)
        assert process.poll() is None, (
            f"Ammeter simulation exited during startup with code {process.returncode}."
        )
        yield
    finally:
        try:
            process.terminate()
            process.wait(timeout=5)
        except OSError:
            if process.poll() is None:
                raise
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

        assert process.poll() is not None, "Ammeter simulation process did not finish after teardown."


@pytest.mark.parametrize("ammeter_type", ["greenlee", "entes"])
def test_sanity(base_config, tmp_path, ammeter_type):
    # init framework
    am_fw = AmmeterTestFramework(base_config)

    # test steps
    samples = am_fw.sampling.get_samples(ammeter_type)

    # collect and organize data for valdations
    performance = am_fw.get_performance_metrics(samples)
    metrics = am_fw.get_statistics(samples)
    sample_result = SampleResult(ammeter_type, samples, metrics, performance)

    # base result validation
    assert samples

    # save results and plots
    am_fw.visualization.plot_sample_result(sample_result, output_directory=tmp_path)
    run_id = am_fw.save_results([sample_result])
    assert run_id


def test_concurrent_sampling(base_config, tmp_path):
    am_fw = AmmeterTestFramework(base_config)
    samples = am_fw.get_all_ammeter_samples()

    sample_results = []
    for ammeter_type, ammeter_samples in samples.items():
        assert ammeter_samples
        performance = am_fw.get_performance_metrics(ammeter_samples)
        metrics = am_fw.get_statistics(ammeter_samples)
        sample_results.append(SampleResult(ammeter_type, ammeter_samples, metrics, performance))


    for sample_result in sample_results:
        am_fw.visualization.plot_sample_result(sample_result, output_directory=tmp_path)
    am_fw.save_results(sample_results)

@pytest.mark.parametrize("sampling_frequency_hz", [50, 500, 5000])
@pytest.mark.parametrize("ammeter_type", ["greenlee"])
def test_ammeter_sampling_performance(base_config, tmp_path, sampling_frequency_hz, ammeter_type):
    duration_seconds = 1
    expected_overrides = {"testing": {"sampling": {"total_duration_seconds": duration_seconds,
                                                   "sampling_frequency_hz": sampling_frequency_hz,
                                                   "measurements_count": None}}}
    config_path = create_config_with_overrides(base_config, expected_overrides, tmp_path)
    am_fw = AmmeterTestFramework(config_path)
    samples = am_fw.sampling.get_samples(ammeter_type)
    performance = am_fw.get_performance_metrics(samples)

    expected_interval = 1 / sampling_frequency_hz
    assert len(samples) >= 2, (
        f"{ammeter_type} at {sampling_frequency_hz} Hz produced {len(samples)} samples; "
        "at least 2 are required to calculate interval performance."
    )
    actual_interval = performance["interval_mean_seconds"]
    assert math.isclose(actual_interval, expected_interval, rel_tol=0.25), (
        f"{ammeter_type} at {sampling_frequency_hz} Hz had mean interval "
        f"{actual_interval:.6g}s; expected {expected_interval:.6g}s "
        "within 25% tolerance."
    )
    actual_jitter = performance["mean_absolute_interval_jitter_seconds"]
    max_jitter = expected_interval * 0.25
    assert actual_jitter <= max_jitter, (
        f"{ammeter_type} at {sampling_frequency_hz} Hz had mean absolute interval "
        f"jitter {actual_jitter:.6g}s; maximum allowed is {max_jitter:.6g}s."
    )
