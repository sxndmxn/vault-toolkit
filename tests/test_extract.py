"""Tests for entity extraction module."""

import pytest

from vault_toolkit.extract.patterns import (
    BUILTIN_PATTERNS,
    compile_patterns,
    extract_with_pattern,
    PatternConfig,
)
from vault_toolkit.extract.entities import extract_entities, aggregate_entities
from vault_toolkit.core.db import connect, table_exists
import re


class TestPatterns:
    """Tests for pattern matching."""

    def test_builtin_email_pattern(self):
        pattern = re.compile(BUILTIN_PATTERNS["email"])
        assert pattern.search("user@example.com")
        assert pattern.search("test.user@company.org")
        assert not pattern.search("invalid-email")

    def test_builtin_ipv4_pattern(self):
        pattern = re.compile(BUILTIN_PATTERNS["ipv4"])
        assert pattern.search("192.168.1.1")
        assert pattern.search("10.0.0.1")
        assert not pattern.search("999.999.999.999")

    def test_builtin_url_pattern(self):
        pattern = re.compile(BUILTIN_PATTERNS["url"])
        assert pattern.search("https://example.com")
        assert pattern.search("http://test.org/path")

    def test_compile_patterns(self):
        config = {
            "entities": {
                "email": {"pattern": BUILTIN_PATTERNS["email"]},
                "custom": {"pattern": r"\bID:\d+\b"},
            }
        }
        compiled = compile_patterns(config)
        assert "email" in compiled
        assert "custom" in compiled

    def test_extract_with_pattern(self):
        pattern = re.compile(BUILTIN_PATTERNS["email"])
        config = PatternConfig(name="email", pattern=BUILTIN_PATTERNS["email"])
        text = "Contact us at user@example.com or support@company.org"

        results = extract_with_pattern(text, pattern, config)
        assert len(results) == 2
        assert any(r["value"] == "user@example.com" for r in results)
        assert any(r["value"] == "support@company.org" for r in results)


class TestEntityExtraction:
    """Tests for entity extraction from database."""

    def test_extract_entities(self, sample_db):
        count = extract_entities(
            str(sample_db),
            "events",
            "message",
            patterns={"ipv4": {"pattern": BUILTIN_PATTERNS["ipv4"]}},
        )
        assert count > 0

        with connect(sample_db) as conn:
            assert table_exists(conn, "entities")

    def test_aggregate_entities(self, sample_db):
        # First extract
        extract_entities(
            str(sample_db),
            "events",
            "message",
            patterns={"ipv4": {"pattern": BUILTIN_PATTERNS["ipv4"]}},
        )

        # Then aggregate
        agg = aggregate_entities(str(sample_db))
        assert not agg.is_empty()
        assert "entity_type" in agg.columns
        assert "value" in agg.columns
        assert "count" in agg.columns
