"""Pattern definitions and extraction utilities."""

import re
from dataclasses import dataclass
from typing import Any


# Built-in patterns for common entity types
BUILTIN_PATTERNS = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "ipv4": r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b",
    "ipv6": r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b",
    "url": r"https?://[^\s<>\"']+",
    "phone_us": r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    "uuid": r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
    "mac_address": r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b",
    "iso_timestamp": r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b",
    "date_ymd": r"\b\d{4}[-/]\d{2}[-/]\d{2}\b",
    "coordinate_decimal": r"\b-?\d{1,3}\.\d+,\s*-?\d{1,3}\.\d+\b",
    "coordinate_dms": r"\b\d{1,3}°\s*\d{1,2}'\s*\d{1,2}(?:\.\d+)?\"?\s*[NSEW]\b",
    "hex_color": r"#[0-9A-Fa-f]{6}\b",
    "md5": r"\b[a-fA-F0-9]{32}\b",
    "sha256": r"\b[a-fA-F0-9]{64}\b",
    "filepath_unix": r"(?:/[\w.-]+)+",
    "filepath_windows": r"[A-Za-z]:\\(?:[\w.-]+\\)*[\w.-]+",
}


@dataclass
class PatternConfig:
    """Configuration for an extraction pattern."""

    name: str
    pattern: str
    normalize: str | None = None  # 'uppercase', 'lowercase', 'strip'
    entity_type: str | None = None  # Override entity type
    validation: str | None = None  # Optional validation regex


def compile_patterns(
    config: dict[str, Any],
) -> dict[str, tuple[re.Pattern, PatternConfig]]:
    """Compile pattern configurations into regex objects.

    Args:
        config: Dictionary with 'entities' key containing pattern configs.

    Returns:
        Dictionary mapping entity names to (compiled pattern, config).
    """
    result = {}
    entities = config.get("entities", {})

    for name, entity_config in entities.items():
        if isinstance(entity_config, str):
            # Simple pattern string
            pattern = entity_config
            cfg = PatternConfig(name=name, pattern=pattern)
        else:
            # Full config dict
            pattern = entity_config.get("pattern", "")

            # Check for built-in pattern reference
            if pattern.startswith("builtin:"):
                builtin_name = pattern[8:]
                pattern = BUILTIN_PATTERNS.get(builtin_name, pattern)

            cfg = PatternConfig(
                name=name,
                pattern=pattern,
                normalize=entity_config.get("normalize"),
                entity_type=entity_config.get("type"),
                validation=entity_config.get("validation"),
            )

        try:
            compiled = re.compile(pattern)
            result[name] = (compiled, cfg)
        except re.error as e:
            raise ValueError(f"Invalid pattern for {name}: {e}")

    return result


def extract_with_pattern(
    text: str,
    pattern: re.Pattern,
    config: PatternConfig,
) -> list[dict[str, Any]]:
    """Extract entities from text using a pattern.

    Args:
        text: Text to extract from.
        pattern: Compiled regex pattern.
        config: Pattern configuration.

    Returns:
        List of extracted entity dictionaries.
    """
    if not text:
        return []

    results = []
    seen = set()

    for match in pattern.finditer(text):
        # Get matched value
        if match.lastgroup:
            value = match.group(match.lastgroup)
        else:
            value = match.group(0)

        # Normalize
        value = _normalize_value(value, config.normalize)

        # Skip duplicates
        if value in seen:
            continue
        seen.add(value)

        # Validate if configured
        if config.validation:
            if not re.match(config.validation, value):
                continue

        results.append({
            "entity_type": config.entity_type or config.name,
            "value": value,
            "start": match.start(),
            "end": match.end(),
        })

    return results


def _normalize_value(value: str, normalize: str | None) -> str:
    """Apply normalization to a value."""
    if normalize is None:
        return value
    if normalize == "uppercase":
        return value.upper()
    if normalize == "lowercase":
        return value.lower()
    if normalize == "strip":
        return value.strip()
    return value


def parse_coordinate(value: str) -> tuple[float, float] | None:
    """Parse a coordinate string into lat/lon tuple.

    Args:
        value: Coordinate string in various formats.

    Returns:
        (latitude, longitude) tuple or None if parsing fails.
    """
    # Try decimal format: "lat, lon"
    decimal_match = re.match(r"(-?\d+\.?\d*),\s*(-?\d+\.?\d*)", value)
    if decimal_match:
        try:
            lat = float(decimal_match.group(1))
            lon = float(decimal_match.group(2))
            return (lat, lon)
        except ValueError:
            pass

    # Try DMS format
    dms_pattern = r"(\d+)°\s*(\d+)'\s*(\d+(?:\.\d+)?)?\"?\s*([NSEW])"
    matches = re.findall(dms_pattern, value)
    if len(matches) >= 2:
        try:
            lat = _dms_to_decimal(*matches[0])
            lon = _dms_to_decimal(*matches[1])
            return (lat, lon)
        except (ValueError, IndexError):
            pass

    return None


def _dms_to_decimal(degrees: str, minutes: str, seconds: str, direction: str) -> float:
    """Convert DMS coordinates to decimal."""
    d = float(degrees)
    m = float(minutes)
    s = float(seconds) if seconds else 0

    decimal = d + m / 60 + s / 3600

    if direction in ("S", "W"):
        decimal = -decimal

    return decimal
