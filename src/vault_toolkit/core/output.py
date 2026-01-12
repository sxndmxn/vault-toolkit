"""Output formatting utilities for console and markdown."""

import sys
from typing import Any, TextIO

import polars as pl


def console(
    message: str,
    *,
    error: bool = False,
    file: TextIO | None = None,
) -> None:
    """Print a message to the console.

    Args:
        message: Message to print.
        error: If True, print to stderr.
        file: Optional file to write to instead of stdout/stderr.
    """
    if file is None:
        file = sys.stderr if error else sys.stdout
    print(message, file=file)


def markdown_table(df: pl.DataFrame, max_rows: int = 50) -> str:
    """Convert a Polars DataFrame to a markdown table.

    Args:
        df: DataFrame to convert.
        max_rows: Maximum number of rows to include.

    Returns:
        Markdown-formatted table string.
    """
    if df.is_empty():
        return "*No data*"

    # Limit rows
    if len(df) > max_rows:
        df = df.head(max_rows)
        truncated = True
    else:
        truncated = False

    # Build header
    columns = df.columns
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"

    # Build rows
    rows = []
    for row in df.iter_rows():
        cells = [_format_cell(cell) for cell in row]
        rows.append("| " + " | ".join(cells) + " |")

    result = "\n".join([header, separator] + rows)

    if truncated:
        result += f"\n\n*... and {len(df) - max_rows} more rows*"

    return result


def _format_cell(value: Any) -> str:
    """Format a cell value for markdown."""
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def ascii_histogram(
    values: list[tuple[str, int]],
    width: int = 32,
    show_values: bool = True,
) -> str:
    """Create an ASCII histogram.

    Args:
        values: List of (label, count) tuples.
        width: Maximum bar width in characters.
        show_values: Whether to show numeric values.

    Returns:
        ASCII histogram string.
    """
    if not values:
        return ""

    max_value = max(v for _, v in values)
    max_label_len = max(len(label) for label, _ in values)

    lines = []
    for label, value in values:
        if max_value > 0:
            bar_len = int((value / max_value) * width)
        else:
            bar_len = 0

        bar = "\u2588" * bar_len + "\u2591" * (width - bar_len)
        padded_label = label.ljust(max_label_len)

        if show_values:
            lines.append(f"{padded_label} {bar} {value:,}")
        else:
            lines.append(f"{padded_label} {bar}")

    return "\n".join(lines)


def format_duration(seconds: float) -> str:
    """Format a duration in seconds to human-readable string.

    Args:
        seconds: Duration in seconds.

    Returns:
        Human-readable duration string.
    """
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.0f}m"
    elif seconds < 86400:
        hours = seconds / 3600
        return f"{hours:.1f}h"
    else:
        days = seconds / 86400
        return f"{days:.1f}d"


def progress_bar(current: int, total: int, width: int = 40, prefix: str = "") -> str:
    """Create a progress bar string.

    Args:
        current: Current progress value.
        total: Total/maximum value.
        width: Width of the progress bar.
        prefix: Optional prefix text.

    Returns:
        Progress bar string.
    """
    if total == 0:
        pct = 100
    else:
        pct = int((current / total) * 100)

    filled = int((current / total) * width) if total > 0 else width
    bar = "\u2588" * filled + "\u2591" * (width - filled)

    return f"{prefix}[{bar}] {pct}% ({current}/{total})"
