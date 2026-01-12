"""TOML configuration loading and validation."""

import tomllib
from pathlib import Path
from typing import Any


def load_config(path: str | Path) -> dict[str, Any]:
    """Load a TOML configuration file.

    Args:
        path: Path to the TOML file.

    Returns:
        Parsed configuration dictionary.

    Raises:
        FileNotFoundError: If the config file doesn't exist.
        tomllib.TOMLDecodeError: If the TOML is invalid.
    """
    path = Path(path)
    with open(path, "rb") as f:
        return tomllib.load(f)


def get_nested(config: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely get a nested configuration value.

    Args:
        config: Configuration dictionary.
        *keys: Sequence of keys to traverse.
        default: Default value if key path doesn't exist.

    Returns:
        The value at the key path, or default.
    """
    current = config
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current


def merge_configs(*configs: dict[str, Any]) -> dict[str, Any]:
    """Deep merge multiple configuration dictionaries.

    Later configs override earlier ones. Nested dicts are merged recursively.

    Args:
        *configs: Configuration dictionaries to merge.

    Returns:
        Merged configuration dictionary.
    """
    result: dict[str, Any] = {}
    for config in configs:
        _deep_merge(result, config)
    return result


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    """Recursively merge override into base dict (in-place)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
