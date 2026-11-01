"""Analysis helpers for sampled ammeter results.

To add a metric:
1. Implement metric calculation -  func(data:iterable) -> any
2. To `METRIC_CALCULATORS` add name and function
3. Add metric name to 'Analysis.SUPPORTED_STATISTICAL_METRICS'

"""

import logging
import numpy as np
from statistics import mean, stdev, median

from src.testing.exceptions import EmptySamplesError, ResultArchiveFilterError



logger = logging.getLogger(__name__)


class ResultAnalyzer:
    """Calculate configured metrics and allow small custom analyzers."""

    METRIC_CALCULATORS = {
        "mean": lambda data: mean(data),
        "median": lambda data: median(data),
        "standard deviation": lambda data: stdev(data),
        "min": lambda data: min(data),
        "max": lambda data: max(data),
        "min max": lambda data: (min(data), max(data)),
    }

    def __init__(self, analysis):
        self.analysis = analysis

    def calculate_metrics(self, samples):
        """Calculate the configured statistical metrics."""
        if not samples:
            raise EmptySamplesError("Cannot calculate statistics for an empty sample set")

        result = {}
        for selected_metrix in self.analysis.statistical_metrics:
            lc_matrix = selected_metrix.lower()
            if lc_matrix in ResultAnalyzer.METRIC_CALCULATORS:
                result[selected_metrix] = ResultAnalyzer.METRIC_CALCULATORS[lc_matrix](samples)
            else:
                logger.warning("Ignoring unsupported statistical metric: %s", selected_metrix)
        return result

    @staticmethod
    def sampling_performance(samples: list[tuple[float, float]], sampling_frequency_hz) -> dict:
        expected_interval = 1.0 / sampling_frequency_hz
        timestamps, currents =  np.array(samples, dtype=float).T
        current_mean = float(np.mean(currents)) if currents.size else 0.0
        current_std = float(np.std(currents)) if currents.size else 0.0
        intervals = np.diff(timestamps)
        jitter = np.abs(intervals - expected_interval)
        return {
            "coefficient_of_variation_percent": (
                float(current_std / abs(current_mean) * 100) if current_mean != 0 else None
            ),
            "interval_mean_seconds": float(np.mean(intervals)) if intervals.size else None,
            "interval_std_seconds": float(np.std(intervals)) if intervals.size else None,
            "mean_absolute_interval_jitter_seconds": float(np.mean(jitter)) if jitter.size else None,
            "max_absolute_interval_jitter_seconds": float(np.max(jitter)) if jitter.size else None,
        }

