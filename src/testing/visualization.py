"""Plot measurement samples and adapt plots to configured test results.

Use :func:`plot_time_series`, :func:`plot_histogram`, or :func:`plot_boxplot`
with timestamp-to-value mappings for standalone plots. Pass ``path_to_save``
to save a PNG; omit it to display the plot using the active Matplotlib backend.

For configured results, initialize :class:`VisualizationManager` with the
framework config and pass a :class:`SampleResult` to ``plot_sample_result``.
To add a plot type, implement a function with the same ``(data, metrics,
path_to_save, title, show)`` arguments, register it in :data:`PLOT_FUNCTIONS`,
and allow its name in the analysis configuration.
"""

from collections.abc import Mapping
from datetime import datetime, timezone
import logging
from pathlib import Path
import re

import matplotlib.pyplot as plt

from src.testing.exceptions import UnsupportedPlotTypeError
from src.testing.result_manager import SampleResult
from src.utils.config import Config


logger = logging.getLogger(__name__)

COLORS = ("tab:red", "tab:green", "tab:purple", "tab:orange", "tab:brown")
STYLES = ("--", "-.", ":", (0, (4, 1, 1, 1)), (0, (1, 1)))


def plot_time_series(data, metrics=None, path_to_save=None,
                    title="Measurement time series", show=False):
    """Plot one or more timestamped sample series and optional metric lines.

    Args:
        data: A non-empty ``{timestamp: value}`` mapping or a mapping of series
            names to timestamp/value mappings.
        metrics: Optional mapping of labels to numeric values. Two-value tuples
            or lists are drawn as separately labeled lower and upper bounds.
        path_to_save: Optional PNG destination. If omitted, display the plot.
        title: Plot title.
        show: Also display the plot when saving it to a path.

    Returns:
        The saved image path, or ``None`` when displayed.
    """
    figure, axis = plt.subplots()
    for name, points in _series(data):
        timestamps, values = zip(*sorted((float(t), float(v)) for t, v in points.items()))
        axis.plot(timestamps, values, marker=".", label=name)
    for index, (name, value) in enumerate(_expand_metrics(metrics or {})):
        axis.axhline(
            value, color=COLORS[index % len(COLORS)],
            linestyle=STYLES[index % len(STYLES)], linewidth=1.5, label=name,
        )
    axis.set(title=title, xlabel="Timestamp", ylabel="Measurement")
    axis.grid(True, alpha=0.3)
    axis.legend()
    return _finish_plot(figure, path_to_save, show)


def plot_histogram(data, metrics=None, path_to_save=None,
                   title="Measurement distribution", xlabel="", ylabel="", show=False):
    """Plot a histogram for each sample series.

    Args:
        data: A non-empty ``{timestamp: value}`` mapping or named mappings of
            timestamp/value pairs.
        metrics: Accepted for compatibility with the common plot function
            signature; histograms do not draw metric lines.
        path_to_save: Optional PNG destination. If omitted, display the plot.
        title: Plot title.
        xlabel: Horizontal axis label.
        ylabel: Vertical axis label.
        show: Also display the plot when saving it to a path.

    Returns:
        The saved image path, or ``None`` when displayed.
    """
    figure, axis = plt.subplots()
    for name, points in _series(data):
        axis.hist([float(value) for value in points.values()], bins="auto", alpha=0.5, label=name)
    axis.set(title=title, xlabel=xlabel, ylabel=ylabel)
    axis.legend()
    return _finish_plot(figure, path_to_save, show)


def plot_boxplot(data, metrics=None, path_to_save=None,
                 title="Measurement summary", show=False):
    """Plot a box-and-whisker summary for each sample series.

    Args:
        data: A non-empty ``{timestamp: value}`` mapping or named mappings of
            timestamp/value pairs.
        metrics: Accepted for compatibility with the common plot function
            signature; box plots do not draw metric lines.
        path_to_save: Optional PNG destination. If omitted, display the plot.
        title: Plot title.
        show: Also display the plot when saving it to a path.

    Returns:
        The saved image path, or ``None`` when displayed.
    """
    series = _series(data)
    figure, axis = plt.subplots()
    values = [[float(value) for value in points.values()] for _, points in series]
    axis.boxplot(values, tick_labels=[name for name, _ in series])
    axis.set(title=title, ylabel="Measurement")
    axis.grid(True, axis="y", alpha=0.3)
    return _finish_plot(figure, path_to_save, show)


def _series(data):
    """Normalize flat, named, or result-wrapped sample mappings to named series."""
    if isinstance(data, Mapping) and "samples" in data:
        data = data["samples"]
    if not isinstance(data, Mapping) or not data:
        raise ValueError("Plot data must be a non-empty mapping")
    if all(isinstance(points, Mapping) for points in data.values()):
        series = [(str(name), points) for name, points in data.items() if points]
        if not series:
            raise ValueError("Plot data must contain at least one sample")
        return series
    return [("Measurement", data)]


def _expand_metrics(metrics):
    """Yield numeric horizontal lines, expanding two-value bounds by label."""
    for name, value in metrics.items():
        if isinstance(value, (tuple, list)) and len(value) == 2:
            yield f"{name} min", float(value[0])
            yield f"{name} max", float(value[1])
        else:
            yield str(name), float(value)


def _finish_plot(figure, path_to_save, show=False):
    """Save and/or display a figure, then always close it."""
    try:
        if path_to_save is None and not show:
            plt.show()
            return None
        saved_path = None
        if path_to_save is not None:
            path = Path(path_to_save)
            path.parent.mkdir(parents=True, exist_ok=True)
            figure.savefig(path, format="png")
            logger.info("Saved plot to %s", path)
            saved_path = str(path)
        if show:
            plt.show()
        return saved_path
    except Exception:
        logger.exception("Could not create plot")
        raise
    finally:
        plt.close(figure)


# def _plot_path(directory: Path, plot_type: str, ammeter_type: str) -> Path:
#     """Build a unique PNG path for one ammeter and plot type."""
#     ammeter = re.sub(r"[^A-Za-z0-9_.-]+", "_", ammeter_type or "measurements")
#     timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
#     return directory / f"{ammeter}_{plot_type}_{timestamp}.png"


class VisualizationManager:
    """Create configured plots for ammeter sample results."""

    def __init__(self, config: Config) -> None:
        """Initialize the manager and reject unsupported configured plot types."""
        self.validate_config(config)
        self.config = config
        self.analysis = config.analysis
        self.output_directory = Path(config.result_management.output_directory)
        self.save_plots = self.analysis.visualization_enabled
        self.show_plots = self.analysis.show_plots and self.save_plots

    @staticmethod
    def validate_config(config: Config) -> None:
        """Raise ``UnsupportedPlotTypeError`` for plot types without renderers."""
        analysis = config.analysis
        visualization = getattr(analysis, "visualization", {})
        configured = visualization.get("plot_types") or analysis.plot_types
        unsupported = set(configured or ()) - PLOT_FUNCTIONS.keys()
        if unsupported:
            names = ", ".join(sorted(unsupported))
            raise UnsupportedPlotTypeError(f"Unsupported visualization plot type(s): {names}")

    def plot_sample_result(
        self,
        sample: SampleResult,
        output_directory: Path | str | None = None,
    ) -> dict[str, str | None]:
        """Plot one sample result using the types selected in the configuration."""
        if not self.save_plots:
            return {}

        directory = Path(output_directory) if output_directory is not None else self.output_directory
        data = {sample.ammeter_type: dict(sample.samples)}
        result: dict[str, str | None] = {}
        visualization = getattr(self.analysis, "visualization", {})
        for plot_type in visualization.get("plot_types") or self.analysis.plot_types:
            plot_function = PLOT_FUNCTIONS[plot_type]
            path = directory / f"{sample.ammeter_type}-{plot_type}.png"

            result[plot_type] = plot_function(
                data=data,
                metrics=sample.metrics if plot_type == "time_series" else None,
                path_to_save=path,
                title=f"{sample.ammeter_type} measurement",
                show=self.show_plots,
            )
            sample.plot_paths.append(path)
        return result

PLOT_FUNCTIONS = {
    "time_series": plot_time_series,
    "histogram": plot_histogram,
    "boxplot": plot_boxplot,
}
