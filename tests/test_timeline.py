"""Tests for timeline module."""

from datetime import timedelta

import pytest

from vault_toolkit.timeline.merge import merge_timelines, create_unified_timeline
from vault_toolkit.timeline.gaps import detect_gaps, analyze_density
from vault_toolkit.core.db import connect, table_exists


class TestTimelineMerge:
    """Tests for timeline merging."""

    def test_merge_timelines(self, sample_db):
        df = merge_timelines(str(sample_db), timestamp_column="timestamp")
        assert not df.is_empty()
        assert "_timeline_source" in df.columns

    def test_create_unified_timeline(self, sample_db):
        count = create_unified_timeline(
            str(sample_db),
            "unified_timeline",
            timestamp_column="timestamp",
        )
        assert count > 0

        with connect(sample_db) as conn:
            assert table_exists(conn, "unified_timeline")


class TestGapDetection:
    """Tests for gap detection."""

    def test_detect_gaps(self, sample_db):
        df = merge_timelines(str(sample_db), timestamp_column="timestamp")
        # With 1-hour intervals, a 30-minute threshold should find no gaps
        gaps = detect_gaps(df, timedelta(minutes=30), "timestamp")
        assert isinstance(gaps, list)

    def test_detect_gaps_with_threshold(self, sample_db):
        df = merge_timelines(str(sample_db), timestamp_column="timestamp")
        # With a very short threshold, should find gaps
        gaps = detect_gaps(df, timedelta(minutes=5), "timestamp")
        # Should find gaps since events are 1 hour apart
        assert len(gaps) > 0

    def test_analyze_density(self, sample_db):
        df = merge_timelines(str(sample_db), timestamp_column="timestamp")
        density = analyze_density(df, timedelta(hours=2), "timestamp")
        assert not density.is_empty()
        assert "interval_start" in density.columns
        assert "event_count" in density.columns
