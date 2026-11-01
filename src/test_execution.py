""" Example for running tests without pytest.
Assumption: that simulator is already running (python ./main.py)

Standalone system checks for the running ammeter simulators.

Run from the repository root with ``python src/test_execution.py`` while the
configured simulator servers are running.
"""

import math
import sys
from pathlib import Path
from statistics import mean, stdev


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.testing.ammeter_sampling import AmmeterSampling
from src.utils.config import load_config
from src.utils.logger import TestLogger


CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
logger = TestLogger("test_execution")


def check_measurement_collection(config, samples_by_ammeter):
    """Check configured simulators return complete, ordered current samples."""
    assert set(samples_by_ammeter) == set(config.ammeters), (
        "Samples must be collected for every configured ammeter"
    )

    for ammeter_type, samples in samples_by_ammeter.items():
        assert len(samples) == config.sampling.measurements_count, (
            f"{ammeter_type} returned {len(samples)} samples; "
            f"expected {config.sampling.measurements_count}"
        )
        assert all(
            math.isfinite(timestamp) and math.isfinite(current)
            for timestamp, current in samples
        ), f"{ammeter_type} returned a non-finite measurement"
        assert all(
            later[0] > earlier[0]
            for earlier, later in zip(samples, samples[1:])
        ), f"{ammeter_type} sample timestamps are not increasing"

    logger.info("PASS: configured ammeters returned complete, ordered measurements")


def check_measurement_precision(samples_by_ammeter):
    """Rank simulator readings by relative spread as a repeatability proxy."""
    coefficient_of_variation = {}
    for ammeter_type, samples in samples_by_ammeter.items():
        currents = [current for _, current in samples]
        assert len(currents) >= 2, f"{ammeter_type} needs at least two readings"

        current_mean = mean(currents)
        current_deviation = stdev(currents)
        assert math.isfinite(current_mean) and current_mean != 0, (
            f"{ammeter_type} mean must be finite and non-zero"
        )
        assert math.isfinite(current_deviation), (
            f"{ammeter_type} standard deviation must be finite"
        )

        coefficient_of_variation[ammeter_type] = (
            current_deviation / abs(current_mean) * 100
        )

    ranking = sorted(coefficient_of_variation.items(), key=lambda item: item[1])
    assert ranking and all(math.isfinite(value) and value >= 0 for _, value in ranking)

    logger.info("Precision ranking (lowest coefficient of variation first):")
    for ammeter_type, value in ranking:
        logger.info(f"  {ammeter_type}: {value:.3f}%")
    logger.info(f"Most repeatable in this run: {ranking[0][0]}")


def main():
    logger.info("Starting configured ammeter system checks")
    try:
        config = load_config(CONFIG_PATH)
        sampler = AmmeterSampling(config.ammeters, config.sampling)
        samples_by_ammeter = {
            ammeter_type: sampler.get_samples(ammeter_type)
            for ammeter_type in config.ammeters
        }

        check_measurement_collection(config, samples_by_ammeter)
        check_measurement_precision(samples_by_ammeter)
        logger.info("All ammeter system checks passed")
    except Exception as exc:
        logger.error(f"Ammeter system checks failed: {exc}")
        raise
    finally:
        logger.close()


if __name__ == "__main__":
    main()
