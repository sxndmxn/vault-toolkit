"""Pytest configuration and fixtures."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from vault_toolkit.core.db import connect, polars_to_table


@pytest.fixture
def temp_db():
    """Create a temporary DuckDB database."""
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as f:
        db_path = Path(f.name)

    yield db_path

    # Cleanup
    db_path.unlink(missing_ok=True)


@pytest.fixture
def sample_events_df():
    """Create sample events DataFrame."""
    base_time = datetime(2025, 1, 10, 0, 0, 0)

    return pl.DataFrame({
        "timestamp": [base_time + timedelta(hours=i) for i in range(10)],
        "source": ["app", "web", "api"] * 3 + ["app"],
        "message": [
            "User login from 192.168.1.1",
            "Request to https://example.com/api",
            "Email sent to user@example.com",
            "Connection from 10.0.0.1",
            "Error: timeout at 192.168.1.100",
            "Visit to https://test.org",
            "Contact: admin@company.com",
            "New session from 172.16.0.1",
            "API call to https://api.service.com",
            "Alert for user@alert.com",
        ],
        "value": [100, 200, 150, 300, 50, 250, 175, 225, 125, 400],
    })


@pytest.fixture
def sample_db(temp_db, sample_events_df):
    """Create a sample database with test data."""
    with connect(temp_db) as conn:
        polars_to_table(conn, sample_events_df, "events")

    return temp_db


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def sample_csv_file(temp_dir):
    """Create a sample CSV file."""
    csv_path = temp_dir / "sample.csv"
    csv_path.write_text(
        "timestamp,source,message,value\n"
        "2025-01-10T00:00:00,app,Test message 1,100\n"
        "2025-01-10T01:00:00,web,Test message 2,200\n"
        "2025-01-10T02:00:00,api,Test message 3,150\n"
    )
    return csv_path


@pytest.fixture
def sample_json_file(temp_dir):
    """Create a sample JSON file."""
    json_path = temp_dir / "sample.json"
    json_path.write_text(
        '[{"ts": 1704844800000, "type": "event", "data": "test1"},'
        '{"ts": 1704848400000, "type": "event", "data": "test2"}]'
    )
    return json_path


@pytest.fixture
def sample_log_file(temp_dir):
    """Create a sample log file."""
    log_path = temp_dir / "sample.log"
    log_path.write_text(
        "[2025-01-10 00:00:00] app: User login from 192.168.1.1\n"
        "[2025-01-10 01:00:00] web: Request received\n"
        "[2025-01-10 02:00:00] api: Response sent\n"
    )
    return log_path
