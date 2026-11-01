import random
from pathlib import Path
from statistics import mean, median, pstdev
from types import SimpleNamespace
from copy import deepcopy

import pytest

from src.testing.exceptions import EmptySamplesError, UnsupportedPlotTypeError
from src.testing.result_analyzer import ResultAnalyzer
from src.testing.result_manager import ResultManager, ResultRecord, SampleResult
from src.testing.visualization import VisualizationManager, plot_time_series


class TestResultAnalyzer:
    """Unit tests for configured result metric calculations."""

    def test_calculate_metrics_returns_configured_statistics(self):
        analyzer = ResultAnalyzer(SimpleNamespace(statistical_metrics=[
            "Mean", "Median", "Standard deviation", "Min", "Max", "Min Max"
        ]))

        metrics = analyzer.calculate_metrics([1, 2, 3, 4])

        assert metrics["Mean"] == pytest.approx(2.5)
        assert metrics["Median"] == pytest.approx(2.5)
        assert metrics["Standard deviation"] == pytest.approx(1.290994)
        assert metrics["Min"] == 1
        assert metrics["Max"] == 4
        assert metrics["Min Max"] == (1, 4)

    def test_calculate_metrics_rejects_empty_samples(self):
        analyzer = ResultAnalyzer(SimpleNamespace(statistical_metrics=["Mean"]))

        with pytest.raises(EmptySamplesError, match="empty sample set"):
            analyzer.calculate_metrics([])

    def test_calculate_metrics_ignores_and_logs_unsupported_metric(self, caplog):
        analyzer = ResultAnalyzer(SimpleNamespace(statistical_metrics=["Mean", "Unsupported metric"]))

        metrics = analyzer.calculate_metrics([2, 4])

        assert metrics == {"Mean": pytest.approx(3)}
        assert "Ignoring unsupported statistical metric: Unsupported metric" in caplog.text


class TestResultManager:
    """Unit tests for disk-backed result persistence and retrieval."""
    @staticmethod
    def generate_random_sample_result(sample_count=10, seed=None):
        """Build a sample result with random 0–10 A measurements."""
        generator = random.Random(seed)
        ammeter_type = random.choice(["Greenlee", "Entes", "circutor"])
        values = [generator.uniform(0.0, 10.0) for _ in range(sample_count)]
        samples = [(float(index), value) for index, value in enumerate(values)]
        metrics = {
            "mean": mean(values),
            "median": median(values),
            "standard_deviation": pstdev(values),
            "min": min(values),
            "max": max(values),
        }
        return SampleResult(ammeter_type, samples, metrics, {"interval_std_seconds": 0.0})

    def test_get_round_trips_record_samples_metrics_and_plot(self, tmp_path):
        plot_source = tmp_path / "source.png"
        plot_source.write_bytes(b"test image")
        sample = self.generate_random_sample_result()
        sample.plot_paths = [str(plot_source)]
        sample2 = self.generate_random_sample_result()
        record = ResultRecord(samples=[deepcopy(sample), deepcopy(sample2)], ammeter_types=["Greenlee"])


        storage = ResultManager(tmp_path / "results")
        storage.save(record)
        metadata = storage.list_results()
        filtered_metadata = storage.list_results({"run_id": record.run_id})
        searched_metadata = storage.search(record.run_id)
        loaded_by_id = storage.get(run_id=record.run_id)
        latest = storage.get_last_results(count=1)

        assert len(metadata) == 1
        assert metadata[0]["run_id"] == record.run_id
        assert metadata[0]["total_sample_count"] == record.total_sample_count
        assert not isinstance(metadata[0], list)
        assert [item["run_id"] for item in filtered_metadata] == [record.run_id]
        assert [item["run_id"] for item in searched_metadata] == [record.run_id]
        assert loaded_by_id
        loaded_by_id = loaded_by_id[0]
        assert loaded_by_id.run_id == record.run_id
        assert loaded_by_id.ammeter_types == record.ammeter_types
        assert loaded_by_id.total_sample_count == record.total_sample_count
        assert loaded_by_id.samples[0].samples == sample.samples
        assert loaded_by_id.samples[0].metrics == sample.metrics
        assert loaded_by_id.samples[0].performance == sample.performance
        assert loaded_by_id.samples[1].samples == sample2.samples
        assert loaded_by_id.samples[1].metrics == sample2.metrics
        assert loaded_by_id.samples[1].performance == sample2.performance
        assert loaded_by_id.samples[0].plot_paths
        assert len(latest) == 1
        assert latest[0].samples[0].samples == sample.samples
        assert all(Path(p).is_file() for p in loaded_by_id.samples[0].plot_paths)
        assert Path(loaded_by_id.samples[0].plot_paths[0]) != plot_source
        assert Path(loaded_by_id.samples[0].plot_paths[0]).read_bytes() == plot_source.read_bytes()

    def test_get_empty_when_no_record_matches(self, tmp_path):
        record = ResultRecord(
            samples=[self.generate_random_sample_result(seed=7)],
            ammeter_types=["Greenlee"],
        )

        storage = ResultManager(tmp_path / "results")
        storage.save(record)
        assert storage.get(ammeter_types=["ENTES"]) == []

    def test_get_last_results_returns_requested_records_in_timestamp_order(self, tmp_path):
        older = ResultRecord(
            samples=[self.generate_random_sample_result(seed=31)],
            ammeter_types=["Greenlee"],
            created_at="2025-01-01T10:00:00+00:00",
        )
        middle = ResultRecord(
            samples=[self.generate_random_sample_result(seed=32)],
            ammeter_types=["Greenlee"],
            created_at="2025-01-01T11:00:00Z",
        )
        newest = ResultRecord(
            samples=[self.generate_random_sample_result(seed=33)],
            ammeter_types=["Entes"],
            created_at="2025-01-01T14:00:00+02:00",
        )

        storage = ResultManager(tmp_path / "results")
        for record in (newest, older, middle):
            storage.save(record)

        latest = storage.get_last_results(count=2)
        no_results = storage.get_last_results(count=0)
        filtered = storage.get_last_results(count=3, filters={"ammeter_types": ["Greenlee"]})

        assert [record.run_id for record in latest] == [middle.run_id, newest.run_id]
        assert no_results == []
        assert [record.run_id for record in filtered] == [older.run_id, middle.run_id]

    def test_delete_removes_only_matching_records(self, tmp_path):
        greenlee_sample = self.generate_random_sample_result(seed=21)
        greenlee_sample.ammeter_type = "Greenlee"
        entes_sample = self.generate_random_sample_result(seed=22)
        entes_sample.ammeter_type = "ENTES"
        greenlee = ResultRecord(samples=[greenlee_sample], ammeter_types=["Greenlee"])
        entes = ResultRecord(samples=[entes_sample], ammeter_types=["ENTES"])

        storage = ResultManager(tmp_path / "results")
        storage.save(greenlee)
        storage.save(entes)
        deleted_count = storage.delete(ammeter_types=["Greenlee"])

        assert deleted_count == 1
        assert not (storage.directory / greenlee.run_id).exists()
        assert len(storage.get(run_id=entes.run_id)) == 1
        remaining = storage.list_results()
        assert len(remaining) == 1
        assert remaining[0]["run_id"] == entes.run_id

    def test_random_sample_result_is_seeded_and_has_calculated_metrics(self):
        sample = self.generate_random_sample_result(sample_count=5, seed=11)
        repeated = self.generate_random_sample_result(sample_count=5, seed=11)
        values = [value for (_, value) in sample.samples]

        assert len(sample.samples) == 5
        assert sample.samples == repeated.samples
        assert sample.metrics["mean"] == mean(values)
        assert sample.metrics["median"] == median(values)
        assert sample.metrics["standard_deviation"] == pstdev(values)


class TestVisualization:
    """Unit tests for standalone and configured plot creation."""

    @staticmethod
    def sample_run():
        return {
            "ammeter_type": "Greenlee",
            "samples": {0.0: 1.0, 0.5: 2.0, 1.0: 1.5},
            "metrics": {"Mean": 1.5, "Min Max": (1.0, 2.0)},
        }

    @classmethod
    def sample_result(cls):
        run = cls.sample_run()
        return SampleResult(run["ammeter_type"], list(run["samples"].items()), run["metrics"])

    @staticmethod
    def config(tmp_path, plot_types, enabled=True):
        analysis = SimpleNamespace(
            visualization={"enabled": enabled, "plot_types": plot_types},
            visualization_enabled=enabled,
            show_plots=False,
            plot_types=plot_types,
        )
        return SimpleNamespace(
            analysis=analysis,
            result_management=SimpleNamespace(output_directory=tmp_path),
        )

    def test_plot_time_series_saves_png(self, tmp_path):
        output_path = tmp_path / "plots" / "current.png"

        result = plot_time_series(
            self.sample_run()["samples"],
            metrics={"Mean": 1.5, "Min Max": (1.0, 2.0)},
            path_to_save=output_path,
        )

        assert result == str(output_path)
        assert output_path.is_file()
        assert output_path.stat().st_size > 0

    @pytest.mark.parametrize("plot_type", ["time_series", "histogram", "boxplot"])
    def test_visualization_manager_dispatches_registered_plot_types(self, tmp_path, plot_type):
        manager = VisualizationManager(self.config(tmp_path, [plot_type]))

        results = manager.plot_sample_result(self.sample_result())

        assert list(results) == [plot_type]
        assert Path(results[plot_type]).is_file()

    def test_visualization_manager_rejects_unsupported_plot_types(self, tmp_path):
        config = self.config(tmp_path, ["unknown_plot"])

        with pytest.raises(UnsupportedPlotTypeError, match="unknown_plot"):
            VisualizationManager(config)

    def test_visualization_manager_does_not_plot_when_disabled(self, tmp_path):
        manager = VisualizationManager(self.config(tmp_path, ["time_series"], enabled=False))

        assert manager.plot_sample_result(self.sample_result()) == {}
