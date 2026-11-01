import os.path
from pathlib import Path

import yaml

from dataclasses import dataclass
import math
from typing import ClassVar, Optional
from src.testing.exceptions import SamplingConfigurationError


class ConfigError(Exception):
    """ General Config error """

class KeyMissingError(ConfigError):
    """ Missing mandatory field in configuration"""

class InvalidConfigValue(ConfigError):
    """A configuration value has the wrong type or is unsupported."""

class InvalidSamplingValue(SamplingConfigurationError, ConfigError):
    """ Invalid one of sample parameters"""


@dataclass
class Sampling:
    measurements_count: int|None
    total_duration_seconds: float|None
    sampling_frequency_hz: float|None

    def __post_init__(self):
        n = self.measurements_count
        t = self.total_duration_seconds
        f = self.sampling_frequency_hz
        provided = sum(1 for x in [n, t, f] if x is not None)
        if provided < 2:
            raise InvalidSamplingValue("At least two sampling values should be provided")
        elif provided == 2:
            try:
                if n is None:
                    self.measurements_count = round(f * t)
                elif t is None:
                    self.total_duration_seconds = n / f
                elif f is None:
                    self.sampling_frequency_hz = n / t
            except (TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
                raise InvalidSamplingValue("Sampling values cannot be resolved") from exc
        elif provided == 3:
            expected_n = round(f * t)
            if expected_n != n:
                raise InvalidSamplingValue("Sampling parameter mismatch")


@dataclass
class AmmeterConfig:
    MIN_PORT: ClassVar[int] = 1
    MAX_PORT: ClassVar[int] = 65535

    port: int
    command: bytes

    def __post_init__(self):
        if isinstance(self.command, str):
            self.command = self.command.encode()
        if not isinstance(self.port, int) or isinstance(self.port, bool) or not self.MIN_PORT <= self.port <= self.MAX_PORT:
            raise InvalidConfigValue(f"Ammeter port must be between {self.MIN_PORT} and {self.MAX_PORT}")
        if not isinstance(self.command, bytes) or not self.command.strip():
            raise InvalidConfigValue("Ammeter command must be a non-empty string or byte sequence")



@dataclass
class Analysis:
    SUPPORTED_STATISTICAL_METRICS: ClassVar[frozenset[str]] = frozenset({
        "mean", "median", "standard deviation", "min", "max", "min max"
    })
    SUPPORTED_PLOT_TYPES: ClassVar[frozenset[str]] = frozenset({
        "time_series", "histogram", "boxplot"
    })

    statistical_metrics: Optional[list[str]] = None
    visualization: Optional[dict] = None
    plot_types: Optional[list[str]] = None

    def __post_init__(self):
        if self.visualization is None:
            self.visualization = {"enabled": False}
        if not isinstance(self.visualization, dict):
            raise InvalidConfigValue("analysis.visualization must be a mapping")
        if not isinstance(self.visualization.get("enabled", False), bool):
            raise InvalidConfigValue("analysis.visualization.enabled must be a boolean")
        visualization_types = self.visualization.get("plot_types")
        if visualization_types is not None:
            self.plot_types = visualization_types

        if self.statistical_metrics is None:
            self.statistical_metrics = ["Mean", "Median", "Standard deviation", "Min Max"]
        if not isinstance(self.statistical_metrics, list) or any(
            not isinstance(metric, str)
            or metric.strip().lower() not in self.SUPPORTED_STATISTICAL_METRICS
            for metric in self.statistical_metrics
        ):
            raise InvalidConfigValue("analysis.statistical_metrics contains an unsupported metric")

        if self.plot_types is None:
            self.plot_types = ["time_series"]
        if not isinstance(self.plot_types, list) or any(
            not isinstance(plot_type, str) or plot_type not in self.SUPPORTED_PLOT_TYPES
            for plot_type in self.plot_types
        ):
            raise InvalidConfigValue("analysis.plot_types contains an unsupported plot type")

    @property
    def visualization_enabled(self):
        return self.visualization.get("enabled", False)

    @property
    def show_plots(self):
        return self.visualization.get("show", False)


@dataclass
class ResultManagement:
    output_directory: str = "results"
    save: bool = True

    def __post_init__(self):
        self.output_directory = os.path.abspath(self.output_directory)
        # if not os.path.isdir(self.output_directory):
        #     raise InvalidConfigValue(f"Invalid output_directory: {self.output_directory}")


@dataclass
class Config:
    sampling: Sampling
    ammeters: dict[str, AmmeterConfig]
    analysis: Analysis
    result_management: ResultManagement


def load_config(config_path: str|Path) -> Config:
    """
    טעינת קובץ הקונפיגורציה
    """
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            config_dict = yaml.safe_load(config_file)

        if not isinstance(config_dict, dict):
            raise InvalidConfigValue("Configuration root must be a mapping")
        testing = config_dict.get("testing", {})
        if not isinstance(testing, dict):
            raise InvalidConfigValue("testing must be a mapping")
        sampling_data = testing.get("sampling", config_dict.get("sampling", {}))
        if not isinstance(sampling_data, dict):
            raise InvalidSamplingValue("testing.sampling must be a mapping")

        sampling = Sampling(**sampling_data)
        ammeter_data = config_dict["ammeters"]
        ammeters = {am_name: AmmeterConfig(**am_values) for am_name, am_values in ammeter_data.items()}
        analysis = Analysis(**config_dict["analysis"])
        result_management = ResultManagement(**config_dict["result_management"])
        return Config(sampling, ammeters, analysis, result_management)
    except ConfigError:
        raise
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Could not load config '{config_path}': {exc}") from exc
    except Exception as exc:
        raise ConfigError(f"Invalid configuration structure or value: {exc}") from exc

