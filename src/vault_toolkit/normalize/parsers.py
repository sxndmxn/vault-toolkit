"""File parsers for various data formats."""

import json
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import polars as pl


def detect_format(path: Path) -> str:
    """Detect file format from extension.

    Args:
        path: Path to the file.

    Returns:
        Format string: 'csv', 'json', 'ndjson', 'xml', or 'text'.
    """
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    elif suffix == ".json":
        # Check if it's NDJSON by reading first two lines
        with open(path, "r") as f:
            first_line = f.readline().strip()
            second_line = f.readline().strip()
            if first_line.startswith("{") and second_line.startswith("{"):
                return "ndjson"
        return "json"
    elif suffix == ".ndjson" or suffix == ".jsonl":
        return "ndjson"
    elif suffix == ".xml":
        return "xml"
    else:
        return "text"


def parse_csv(
    path: Path,
    *,
    delimiter: str = ",",
    has_header: bool = True,
    schema: dict[str, pl.DataType] | None = None,
) -> pl.DataFrame:
    """Parse a CSV file into a Polars DataFrame.

    Args:
        path: Path to the CSV file.
        delimiter: Column delimiter character.
        has_header: Whether the file has a header row.
        schema: Optional schema override.

    Returns:
        Polars DataFrame with parsed data.
    """
    return pl.read_csv(
        path,
        separator=delimiter,
        has_header=has_header,
        schema=schema,
        try_parse_dates=True,
        infer_schema_length=10000,
    )


def parse_json(path: Path, *, json_path: str | None = None) -> pl.DataFrame:
    """Parse a JSON file into a Polars DataFrame.

    Args:
        path: Path to the JSON file.
        json_path: Optional JSON path to extract (e.g., "data.items").

    Returns:
        Polars DataFrame with parsed data.
    """
    with open(path, "r") as f:
        data = json.load(f)

    # Navigate to nested path if specified
    if json_path:
        for key in json_path.split("."):
            if isinstance(data, dict):
                data = data.get(key, [])
            elif isinstance(data, list) and key.isdigit():
                data = data[int(key)]
            else:
                data = []

    # Ensure we have a list of records
    if isinstance(data, dict):
        data = [data]
    elif not isinstance(data, list):
        data = []

    if not data:
        return pl.DataFrame()

    return pl.DataFrame(data)


def parse_ndjson(path: Path) -> pl.DataFrame:
    """Parse a newline-delimited JSON file into a Polars DataFrame.

    Args:
        path: Path to the NDJSON file.

    Returns:
        Polars DataFrame with parsed data.
    """
    return pl.read_ndjson(path)


def parse_xml(
    path: Path,
    *,
    record_tag: str | None = None,
    flatten: bool = True,
) -> pl.DataFrame:
    """Parse an XML file into a Polars DataFrame.

    Args:
        path: Path to the XML file.
        record_tag: Tag name for record elements. If None, uses root's children.
        flatten: Whether to flatten nested elements.

    Returns:
        Polars DataFrame with parsed data.
    """
    tree = ElementTree.parse(path)
    root = tree.getroot()

    # Find record elements
    if record_tag:
        records = root.findall(f".//{record_tag}")
    else:
        records = list(root)

    # Convert to list of dicts
    data = []
    for record in records:
        row = _element_to_dict(record, flatten=flatten)
        data.append(row)

    if not data:
        return pl.DataFrame()

    return pl.DataFrame(data)


def _element_to_dict(element: ElementTree.Element, flatten: bool = True) -> dict:
    """Convert an XML element to a dictionary."""
    result = dict(element.attrib)

    for child in element:
        if len(child) == 0:
            # Leaf node
            result[child.tag] = child.text
        elif flatten:
            # Flatten nested elements with prefix
            nested = _element_to_dict(child, flatten=True)
            for key, value in nested.items():
                result[f"{child.tag}_{key}"] = value
        else:
            result[child.tag] = _element_to_dict(child, flatten=False)

    return result


def parse_regex(
    path: Path,
    pattern: str,
    *,
    encoding: str = "utf-8",
    skip_unmatched: bool = True,
) -> pl.DataFrame:
    """Parse a text file using a regex pattern with named groups.

    Args:
        path: Path to the text file.
        pattern: Regex pattern with named groups.
        encoding: File encoding.
        skip_unmatched: Whether to skip lines that don't match.

    Returns:
        Polars DataFrame with captured groups as columns.
    """
    compiled = re.compile(pattern)
    records = []

    with open(path, "r", encoding=encoding) as f:
        for line_num, line in enumerate(f, 1):
            match = compiled.search(line)
            if match:
                record = match.groupdict()
                record["_line_num"] = line_num
                record["_raw"] = line.rstrip()
                records.append(record)
            elif not skip_unmatched:
                records.append({"_line_num": line_num, "_raw": line.rstrip()})

    if not records:
        return pl.DataFrame()

    return pl.DataFrame(records)


def parse_file(
    path: Path,
    *,
    parser: str | None = None,
    **kwargs: Any,
) -> pl.DataFrame:
    """Parse a file using the appropriate parser.

    Args:
        path: Path to the file.
        parser: Parser to use. If None, auto-detect.
        **kwargs: Additional arguments passed to the parser.

    Returns:
        Polars DataFrame with parsed data.
    """
    if parser is None:
        parser = detect_format(path)

    parsers = {
        "csv": parse_csv,
        "json": parse_json,
        "ndjson": parse_ndjson,
        "xml": parse_xml,
        "regex": parse_regex,
        "text": parse_regex,
    }

    parse_fn = parsers.get(parser)
    if parse_fn is None:
        raise ValueError(f"Unknown parser: {parser}")

    # Filter kwargs to only those accepted by the parser
    return parse_fn(path, **kwargs)
