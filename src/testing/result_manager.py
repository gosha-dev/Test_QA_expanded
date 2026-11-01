"""Disk-backed storage for measurement result records."""

import csv
import json
import logging
import re
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

import src.testing.exceptions as ex

logger = logging.getLogger(__name__)


@dataclass
class SampleResult:
    """One timestamped measurement series with analysis and an optional plot. """
    ammeter_type: str
    samples: list[tuple[float, float]]
    metrics: Mapping[str, Any] = field(default_factory=dict)
    performance: Mapping[str, Any] = field(default_factory=dict)
    samples_count: Optional[int] = None
    plot_paths: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.samples_count:
            self.samples_count = len(self.samples)


@dataclass
class ResultRecord:
    """In-memory representation of one measurement test run."""

    samples: list[SampleResult]
    run_id: str = ''
    created_at: str = ''
    ammeter_types: list[str] | None = None
    total_sample_count: int = 0
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.run_id:
            self.run_id = uuid.uuid4().hex
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if self.ammeter_types is None:
            self.ammeter_types = [smpl.ammeter_type for smpl in self.samples]
        if not self.total_sample_count:
            self.total_sample_count = sum(smpl.samples_count for smpl in self.samples)

class ResultManager:
    """Context-managed database-like storage for ``ResultRecord`` objects."""

    METADATA_FILE = "metadata.json"
    SAMPLES_NAME = "samples.csv"

    def __init__(self, directory: str | Path) -> None:
        """Create storage for a directory.

        Args:
            directory: Root directory containing one subdirectory per run.
        """
        self.directory = Path(directory)

    def save(self, record: ResultRecord) -> str:
        """Persist a ``ResultRecord`` and copy its sample plots into the run directory.

        Args:
            record: The complete record to save. Its ``samples`` must be a list of
                ``SampleResult`` instances.

        Returns:
            The saved record's run ID.
        """
        if not isinstance(record, ResultRecord):
            raise TypeError("record must be a ResultRecord; use save_from_fields() to provide fields")

        run_directory = self.directory / record.run_id
        run_directory.mkdir(parents=True)

        self._write_sample_results(run_directory, record.samples)
        self._dump_metadata(run_directory / self.METADATA_FILE, asdict(record))
        logger.info(f"Saved result {record.run_id} in {run_directory}")
        return record.run_id

    def save_from_sample_results(self, sample_results: list[SampleResult]) -> str:
        """ Create Record and save it.

        Args:
            sample_results: Results.

        Returns:
            The generated record's run ID.
        """

        return self.save(ResultRecord(sample_results))

    def list_results(self, filters: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        """List metadata-only records, optionally filtered by record fields.

        Args:
            filters: Optional run-level metadata filters.

        Returns:
            Matching run-level metadata dictionaries without sample metadata.
        """
        records = [self._load_metadata(path)
                   for path in self.directory.glob(f"*/{self.METADATA_FILE}")]
        return [record for record in records if self._matches(record, filters or {})]

    def get(self, filters: Mapping[str, Any] | None = None, **criteria: Any) -> list[ResultRecord]:
        """Load records matching metadata filters.

        Args:
            filters: Optional mapping of run-level metadata fields.
            **criteria: Additional run-level criteria such as ``run_id``.
        Returns:
            Matching records with their sample readings loaded; an empty list if
            nothing matches.
        """
        query = {**(filters or {}), **criteria}
        return self._load_records(self.list_results(query))

    def get_last_results(self, count: int = 1, filters: Mapping[str, Any] | None = None) -> list[ResultRecord]:
        """Load up to ``count`` the newest records matching optional metadata filters.

        Args:
            count: Maximum number of full records to return.
            filters: Optional record metadata filters.
        Returns:
            Up to ``count`` matching records with samples loaded, ordered oldest
            to newest.
        """
        records = self.list_results(filters)
        if count <= 0 or not records:
            return []
        ordered_records = sorted(records, key=self._created_at_sort_key)
        return self._load_records(ordered_records[-count:])

    @staticmethod
    def _created_at_sort_key(record: Mapping[str, Any]) -> tuple[int, datetime]:
        """Return a UTC timestamp sort key, treating invalid dates as oldest."""
        created_at = record.get("created_at")
        try:
            timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            return 1, timestamp.astimezone(timezone.utc)
        except (AttributeError, TypeError, ValueError):
            return 0, datetime.min.replace(tzinfo=timezone.utc)

    def search(self, query: str) -> list[dict[str, Any]]:
        """Search serialized metadata case-insensitively without loading samples.

        Args:
            query: Text to find in run-level metadata.

        Returns:
            Matching metadata-only records.
        """
        text = str(query).lower()
        return [
            record
            for record in self.list_results()
            if text in json.dumps(record, default=str).lower()
        ]

    def delete(self, filters: Mapping[str, Any] | None = None, **criteria: Any) -> int:
        """Delete matching run directories and return the number removed.

        Args:
            filters: Optional mapping of metadata fields and date constraints.
            **criteria: Additional exact metadata filters. With no filters, all
                records in this storage directory are deleted.

        Returns:
            Number of record directories deleted.
        """
        query = {**(filters or {}), **criteria}
        records = self.list_results(query)
        for record in records:
            shutil.rmtree(self.directory / record["run_id"])
        return len(records)

    def _load_records(self, records_metadata: list[dict[str, Any]]) -> list[ResultRecord]:
        """Load complete records for metadata summaries returned by ``list_results``.

        Args:
            records_metadata: Run-level metadata dictionaries containing ``run_id``.

        Returns:
            Full records with sample readings loaded from their CSV files.
        """
        result_records: list[ResultRecord] = []
        for summary in records_metadata:
            run_directory = self.directory / summary["run_id"]
            record_data = self._load_metadata(run_directory / self.METADATA_FILE)
            record_data["samples"] = self._sample_results(
                record_data.get("samples", []), run_directory
            )
            result_records.append(ResultRecord(**record_data))
        return result_records

    @staticmethod
    def _load_samples(samples_path: Path) -> list[tuple[float, float]]:
        """Load timestamp/current pairs from a sample CSV file."""

        with samples_path.open(newline="", encoding="utf-8") as source:
            reader = csv.reader(source)
            next(reader, None)  # read headers

            return [tuple(map(float, row)) for row in reader]

    def _write_sample_results(self, run_dir: Path, samples: list[SampleResult]) -> None:
        """Write sample readings to CSV files and copy plots into the run directory."""
        for index, sample in enumerate(samples, 1):
            if sample.plot_paths:
                new_paths = []
                for ext_path in sample.plot_paths:
                    in_path = run_dir / Path(ext_path).name
                    new_paths.append(in_path.name)
                    if ext_path != in_path:
                        shutil.copy2(ext_path, in_path)
                sample.plot_paths = new_paths  # overwrite Path

            samples_path = run_dir / self._scv_file_name(index, sample.ammeter_type)
            with samples_path.open("w", newline="", encoding="utf-8") as output:
                writer = csv.writer(output)
                writer.writerow(["timestamp", "current"])
                writer.writerows(sample.samples)
            sample.samples = samples_path.name  # #overwrite samples

    def _sample_results(self, samples_data: list[dict[str, Any]], run_dir: Path) -> list[SampleResult]:
        """Build sample results from metadata descriptors and CSV readings."""
        sample_results: list[SampleResult] = []
        for index, sample_dict in enumerate(samples_data, 1):
            sample_data = dict(sample_dict)
            sample_full_path = run_dir / self._scv_file_name(index, sample_data['ammeter_type'])
            sample_data["samples"] = self._load_samples(sample_full_path)
            sample_data["plot_paths"] = [run_dir / path for path in sample_data["plot_paths"]]
            sample_results.append(SampleResult(**sample_data))

        return sample_results

    def _scv_file_name(self, index: int, ammeter_type: str) -> str:
        return f"{index}_{ammeter_type}_{self.SAMPLES_NAME}"

    @staticmethod
    def _matches(record: Mapping[str, Any], filters: Mapping[str, Any]) -> bool:
        """Return whether run-level metadata satisfies all supplied filters."""
        try:
            for key, expected in filters.items():
                key = key.lower()
                if key in ['ammeter_type', 'type']:
                    if expected not in record.get("ammeter_types"):
                        return False
                if key == "created_at":
                    if not record.get("created_at",'').startswith(expected):
                        return False
                elif key in record:
                    if record[key] != expected:
                        return False
                else:
                    raise ex.FilerNotSupportedError(f"Invalid key in filter {key}")
            return True
        except Exception as err:
            raise ex.ResultArchiveFilterError(f"list results Error {err}") from err

    @staticmethod
    def _dump_metadata(path: Path | str, value: dict[str, Any]) -> None:
        """Serialize a metadata mapping as indented JSON at ``path``."""
        try:
            Path(path).write_text(json.dumps(value, indent=2), encoding="utf-8")
        except Exception as err:
            raise ex.ResultArchiveError(f"Error writing to {path}: {err}")

    @staticmethod
    def _load_metadata(path: Path | str) -> dict[str, Any]:
        """Read a metadata JSON object from ``path``."""
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as err:
            raise ex.ResultArchiveError(f"Error reading from {path}: {err}")

    def _read_metadata(self, path: Path) -> dict[str, Any]:
        """Read run-level metadata, excluding per-sample metadata and readings."""
        metadata = self._load_metadata(path)
        return {key: value for key, value in metadata.items() if key != "samples"}

    def _sample_name(self, directory: Path, ammeter_type: str):
        """ Build a unique name for store samples. """
        ammeter = re.sub(r"[^A-Za-z0-9_.-]+", "_", ammeter_type)
        timestamp = datetime.now(timezone.utc).strftime("%H%M%S_%f")[:-3]
        return directory / f"{ammeter}_{timestamp}_{self.SAMPLES_NAME}"

        def _plot_path(directory: Path, plot_type: str, ammeter_type: str) -> Path:
            """Build a unique PNG path for one ammeter and plot type."""
            ammeter = re.sub(r"[^A-Za-z0-9_.-]+", "_", ammeter_type or "measurements")
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
            return directory / f"{ammeter}_{plot_type}_{timestamp}.png"

