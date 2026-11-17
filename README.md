# Vault Toolkit

Offline-first data analysis tools. No network dependencies, portable, composable.

## Installation

Use Python 3.11 or newer.
Run these commands from the repository root.

```bash
# Using uv (recommended)
uv sync --locked

# Or use pip inside an active virtual environment
pip install -e .
```

With uv, prefix the commands below with `uv run`, such as `uv run vt --help`.

## Quick Start

```bash
# Ingest data
vt normalize --input ./data/ --db analysis.duckdb

# Search across all data
vt search --db analysis.duckdb "keyword"

# Create unified timeline
vt timeline --db analysis.duckdb --gaps --threshold 5m

# Extract entities
vt extract --db analysis.duckdb --table events --field message --builtin email --builtin ipv4

# Find correlations
vt correlate --db analysis.duckdb --config correlate.toml

# Build relationship graph
vt graph --db analysis.duckdb --ascii

# Detect anomalies
vt anomaly --db analysis.duckdb --table events --method zscore --feature value

# Generate report
vt report --db analysis.duckdb --quick
```

## Tools

| Tool | Description |
|------|-------------|
| `vt normalize` | Ingest CSV, JSON, NDJSON, XML, logs into DuckDB |
| `vt search` | Full-text search across all tables |
| `vt timeline` | Merge events, detect gaps, visualize density |
| `vt extract` | Extract entities (emails, IPs, URLs, etc.) |
| `vt correlate` | Find temporal/spatial relationships |
| `vt graph` | Build and visualize entity networks |
| `vt anomaly` | Statistical and behavioral anomaly detection |
| `vt report` | Generate markdown reports |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        DuckDB                               │
│                   (single file store)                       │
└─────────────────────────────────────────────────────────────┘
        ▲           ▲           ▲           ▲
        │           │           │           │
   ┌────┴───┐ ┌─────┴────┐ ┌────┴────┐ ┌────┴────┐
   │normalize│ │ timeline │ │ correlate│ │ search │
   └────────┘ └──────────┘ └─────────┘ └─────────┘
        ▲
        │
   raw data (csv, json, xml, logs)
```

All tools read/write to the same DuckDB file. Config via TOML. Output to stdout or markdown.

## Configuration

See `examples/configs/` for configuration file examples:

- `normalize.toml` - Data ingestion settings
- `extract.toml` - Entity extraction patterns
- `correlate.toml` - Correlation rules
- `anomaly.toml` - Anomaly detection settings
- `report.toml` - Report templates

## Development

```bash
# Install with dev dependencies
uv sync --locked --extra dev

# Run tests
uv run pytest

# Run specific test
uv run pytest tests/test_normalize.py -v
```

## Tech Stack

| Component | Choice |
|-----------|--------|
| Language | Python 3.11+ |
| Data frames | Polars |
| Storage | DuckDB |
| CLI | Click |
| Config | TOML |
| ML | scikit-learn |

## License

MIT
