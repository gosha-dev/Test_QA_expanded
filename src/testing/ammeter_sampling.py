import logging
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Callable

from Ammeters.client import request_current_from_ammeter
from src.testing.exceptions import UnknownAmmeterError, MeasurementAcquisitionError, AmmeterTestError
from src.utils.config import AmmeterConfig, Sampling


logger = logging.getLogger(__name__)


class AmmeterSampling:

    def __init__(self, ammeters: dict[str, AmmeterConfig], sampling_config: Sampling):
        self.ammeters = ammeters
        self.sampling_config = sampling_config

    def _get_ammeter_result(self, ammeter_type: str):
        if ammeter_type not in self.ammeters:
            raise UnknownAmmeterError(f"Unknown ammeter type: {ammeter_type}")
        try:
            ammeter = self.ammeters[ammeter_type]
            return request_current_from_ammeter(ammeter.port, ammeter.command)
        except Exception as exc:
            logger.exception("Measurement acquisition failed for %s", ammeter_type)
            raise MeasurementAcquisitionError(f"Failed to acquire current from {ammeter_type}: {exc}") from exc

    def concurrent_sampling(self, ammeter_types: list[str]) -> dict[str, list]:
        if len(ammeter_types) != len(set(ammeter_types)):
            raise AmmeterTestError("Duplicated ammeter_types in concurrent!!")

        with ThreadPoolExecutor() as pool:
            futures = {am_type: pool.submit(self.get_samples, am_type) for am_type in ammeter_types}
            res = {ammeter_type: future.result() for ammeter_type, future in futures.items()}
        return res

    def get_samples(self, ammeter_type: str) -> list[tuple[float, float]]:
        """Collect measurements on monotonic deadlines without cumulative drift."""
        logger.info("Starting sampling for %s (%s measurements)",
                    ammeter_type, self.sampling_config.measurements_count)
        sampling_func = partial(self._get_ammeter_result, ammeter_type)
        if self.sampling_config.sampling_frequency_hz < 200:  # The minimal accurate sleep time in python is 5ms (1/200)
            samples = self._low_frequency_sampling(sampling_func)
        else:
            samples = self._high_frequency_sampling(sampling_func)
        logger.info("Completed sampling for %s (%s measurements)", ammeter_type, len(samples))
        return samples

    def __next_sample_time(self, init_time:int|float):
        """Yield monotonic deadlines using configured count and frequency."""
        last_time = init_time
        period = 1 / self.sampling_config.sampling_frequency_hz
        for n in range(self.sampling_config.measurements_count):
            yield last_time
            last_time += period

    def _low_frequency_sampling(self, sampling_func: Callable) -> list[tuple[float, float]]:
        """ Simple low frequency sampling
            not suitable for frequency > 200 Hz because sleep(0.005) is not accurate
        """
        res = []
        for next_time in self.__next_sample_time(time.time()):
            if next_time > time.time():
                time.sleep(next_time - time.time())
            res.append((time.time(), sampling_func()))

        return res

    def _high_frequency_sampling(self, sampling_func: Callable) -> list[tuple[float, float]]:
        """ Very high load but better sampling accuracy with active wait """
        res = []
        for next_expected_time in self.__next_sample_time(time.time()):
            while (sample_time := time.time()) < next_expected_time:
                pass
            res.append((sample_time, sampling_func()))

        return res


