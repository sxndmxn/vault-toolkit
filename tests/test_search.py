"""Tests for search module."""

import pytest

from vault_toolkit.search.index import search, search_regex


class TestSearch:
    """Tests for full-text search."""

    def test_search_basic(self, sample_db):
        results = search(str(sample_db), "login")
        assert not results.is_empty()
        assert "login" in results["_match"][0].lower()

    def test_search_ip_address(self, sample_db):
        results = search(str(sample_db), "192.168")
        assert not results.is_empty()

    def test_search_email(self, sample_db):
        results = search(str(sample_db), "example.com")
        assert not results.is_empty()

    def test_search_regex(self, sample_db):
        results = search_regex(str(sample_db), r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")
        assert not results.is_empty()

    def test_search_no_results(self, sample_db):
        results = search(str(sample_db), "nonexistentterm12345")
        assert results.is_empty()

    def test_search_specific_table(self, sample_db):
        results = search(str(sample_db), "login", tables=["events"])
        assert not results.is_empty()
        assert all(r == "events" for r in results["_table"].to_list())
