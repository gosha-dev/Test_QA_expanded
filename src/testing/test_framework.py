import logging

from pathlib import Path

import yaml

from src.testing.ammeter_sampling import AmmeterSampling
from src.testing.result_manager import ResultManager, SampleResult
from src.testing.result_analyzer import ResultAnalyzer
from src.testing.visualization import VisualizationManager
from src.utils.config import load_config


logger = logging.getLogger(__name__)

class AmmeterTestFramework:
    def __init__(self, config_path:str|Path):
        self.config = load_config(config_path)
        self.test_result_dir = Path(self.config.result_management.output_directory)
        self.result_manager = ResultManager(self.test_result_dir)
        self.result_analyzer = ResultAnalyzer(self.config.analysis)
        self.sampling = AmmeterSampling(self.config.ammeters, self.config.sampling)
        self.visualization = VisualizationManager(self.config)

    def run_test(self, ammeter_type: str) -> str:
        logger.info("START ammeter run: %s", ammeter_type)
        samples = self.sampling.get_samples(ammeter_type)
        performance = self.get_performance_metrics(samples)
        metrics = self.get_statistics(samples)


        self.visualization.plot_sample_result(
            SampleResult(ammeter_type, samples, metrics, performance)
        )

        run_id = self.save_results(samples, ammeter_type, metrics, performance)
        logger.info("PASS ammeter run: %s (result %s)", ammeter_type, run_id)
        return run_id

    def get_ammeter_samples(self, ammeter_type: str) -> list:
        return self.sampling.get_samples(ammeter_type)

    def get_all_ammeter_samples(self) -> dict[str, list]:
        return self.sampling.concurrent_sampling(list(self.config.ammeters.keys()))

    def get_performance_metrics(self, samples: list[tuple[float, float]]) -> dict[str, float]:
        return self.result_analyzer.sampling_performance(samples, self.config.sampling.sampling_frequency_hz)

    def get_statistics(self, samples):
        """Delegate statistical analysis to the result manager."""
        return self.result_analyzer.calculate_metrics([value for _, value in samples])

    def save_results(self, sample_results:list[SampleResult]) -> str:
        return self.result_manager.save_from_sample_results(sample_results)

    def list_history_results(self) -> list:
        return self.result_manager.list_results()

    def get_results_by_id(self, run_id: str) -> list:
        return self.result_manager.get(run_id=run_id)

    def compare_runs(self, run_ids: list[str]) -> dict:
        pass


def create_config_with_overrides(config_yaml_path, expected_overrides, temp_dir):
    """Write a temporary YAML config with expected overrides and return its path."""

    def _merge_config(config, overrides):
        """Recursively apply nested overrides to a loaded YAML configuration."""
        for key, value in overrides.items():
            if isinstance(value, dict) and isinstance(config.get(key), dict):
                _merge_config(config[key], value)
            else:
                config[key] = value

    with Path(config_yaml_path).open("r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)

    if expected_overrides:
        _merge_config(config, expected_overrides)

    edited_path = Path(temp_dir) / "config.yaml"
    with edited_path.open("w", encoding="utf-8") as config_file:
        yaml.safe_dump(config, config_file, sort_keys=False)
    return edited_path