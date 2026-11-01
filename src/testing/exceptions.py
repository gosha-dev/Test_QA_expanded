"""Domain-specific errors raised by the ammeter testing framework."""


class AmmeterTestError(Exception):
    """Base class for expected ammeter testing failures."""


class UnknownAmmeterError(AmmeterTestError):
    """The requested ammeter is not present in the configuration."""

# Sampling errors
class SamplingConfigurationError(AmmeterTestError):
    """Sampling settings are missing or inconsistent."""


class EmptySamplesError(AmmeterTestError):
    """Analysis was requested without any samples."""

# result analyzer errors
class UnsupportedMetricError(AmmeterTestError):
    """A configured statistical metric is not supported."""


class UnsupportedPlotTypeError(AmmeterTestError):
    """A configured visualization type is not supported."""


class MeasurementAcquisitionError(AmmeterTestError):
    """A measurement could not be acquired from an ammeter."""


# Result management errors
class ResultArchiveError(AmmeterTestError):
    """A result could not be written to or read from the archive."""

class ResultArchiveFilterError(AmmeterTestError):
    """A result could not be written to or read from the archive."""


class ResultNotFoundError(AmmeterTestError):
    """A requested historical run is not available."""


class FilerNotSupportedError(AmmeterTestError):
    """A requested historical run is not available."""


# Test errors
class InvalidComparisonError(AmmeterTestError):
    """A historical comparison request is invalid."""
