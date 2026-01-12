"""Tests for normalization module."""

import polars as pl
import pytest

from vault_toolkit.normalize.parsers import parse_csv, parse_json, parse_regex, detect_format
from vault_toolkit.normalize.timestamps import parse_timestamp, normalize_timestamp
from vault_toolkit.normalize.ingest import ingest_files
from vault_toolkit.core.db import connect, list_tables


class TestParsers:
    """Tests for file parsers."""

    def test_detect_format_csv(self, temp_dir):
        csv_file = temp_dir / "test.csv"
        csv_file.write_text("a,b,c\n1,2,3")
        assert detect_format(csv_file) == "csv"

    def test_detect_format_json(self, temp_dir):
        json_file = temp_dir / "test.json"
        json_file.write_text('{"key": "value"}')
        assert detect_format(json_file) == "json"

    def test_parse_csv(self, sample_csv_file):
        df = parse_csv(sample_csv_file)
        assert len(df) == 3
        assert "timestamp" in df.columns
        assert "source" in df.columns
        assert "message" in df.columns
        assert "value" in df.columns

    def test_parse_json(self, sample_json_file):
        df = parse_json(sample_json_file)
        assert len(df) == 2
        assert "ts" in df.columns
        assert "type" in df.columns

    def test_parse_regex(self, sample_log_file):
        pattern = r'^\[(?P<timestamp>[^\]]+)\] (?P<source>\w+): (?P<message>.*)'
        df = parse_regex(sample_log_file, pattern)
        assert len(df) == 3
        assert "timestamp" in df.columns
        assert "source" in df.columns
        assert "message" in df.columns


class TestTimestamps:
    """Tests for timestamp handling."""

    def test_parse_timestamp_iso(self):
        result = parse_timestamp("2025-01-10T00:00:00")
        assert result is not None
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 10

    def test_parse_timestamp_epoch(self):
        result = parse_timestamp(1704844800, format="epoch")
        assert result is not None

    def test_parse_timestamp_epoch_ms(self):
        result = parse_timestamp(1704844800000, format="epoch_ms")
        assert result is not None

    def test_normalize_timestamp_column(self, sample_events_df):
        df = sample_events_df.with_columns(
            pl.col("timestamp").dt.strftime("%Y-%m-%d %H:%M:%S").alias("ts_str")
        )
        result = normalize_timestamp(df, "ts_str", format="%Y-%m-%d %H:%M:%S")
        assert result["ts_str"].dtype == pl.Datetime


class TestIngest:
    """Tests for data ingestion."""

    def test_ingest_csv(self, temp_db, sample_csv_file):
        results = ingest_files(sample_csv_file, temp_db)
        assert "sample" in results
        assert results["sample"] == 3

        with connect(temp_db) as conn:
            tables = list_tables(conn)
            assert "sample" in tables

    def test_ingest_directory(self, temp_db, temp_dir, sample_csv_file):
        results = ingest_files(temp_dir, temp_db)
        assert len(results) > 0
