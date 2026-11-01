# Saved Test Results

`ResultManager` creates one directory per saved test run under the configured result output directory. Each run directory contains metadata, the sampled readings, and any plots generated for the run.

## Run Directory Structure

```text
results/
└── <run_id>/
    ├── metadata.json
    ├── 1_greenlee_samples.csv
    ├── greenlee-time_series.png
    ├── 2_entes_samples.csv
    └── entes-time_series.png
```

The run ID is generated when the result is saved. A run may contain one or several ammeter results. Each ammeter has its own CSV file and may have one or more configured plot files.

## Metadata

`metadata.json` describes the run and references the files in its directory. A shortened example:

```json
{
  "samples": [
    {
      "ammeter_type": "greenlee",
      "samples": "1_greenlee_samples.csv",
      "metrics": {
        "Mean": 0.42,
        "Min Max": [0.08, 1.15]
      },
      "performance": {
        "interval_mean_seconds": 0.1,
        "mean_absolute_interval_jitter_seconds": 0.0002
      },
      "samples_count": 50,
      "plot_paths": ["greenlee-time_series.png"]
    }
  ],
  "run_id": "<run_id>",
  "created_at": "2026-01-15T12:30:00+00:00",
  "ammeter_types": ["greenlee"],
  "total_sample_count": 50,
  "schema_version": 1
}
```

The `samples` field in each ammeter entry is the CSV filename. `plot_paths` contains the plot filenames copied into the run directory. Metrics and performance values are stored with the ammeter entry; run-level fields identify the run and summarize its sample count.

## Sample Data

Each CSV contains timestamp and current columns, with one measurement per row:

```csv
timestamp,current
1793534681.1388738,0.42
1793534681.2389388,0.39
```

The numbered filename distinguishes each ammeter's sample file within a run. Plot filenames use the ammeter name and plot type, such as `greenlee-time_series.png`. `ResultManager` copies generated plots into the run directory when it archives the result.
