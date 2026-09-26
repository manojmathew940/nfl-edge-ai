"""File helpers shared by ingestion and cleaning: safe replacement and metadata files."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterator


@contextmanager
def staged_output(output_path: Path) -> Iterator[Path]:
    """Yield a temporary path that replaces output_path only on success.

    The temporary file lives next to the output so the final rename is atomic.
    An existing output is left untouched if the block raises.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "wb", dir=output_path.parent, prefix=f".{output_path.stem}.", delete=False
    ) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        yield temp_path
        temp_path.replace(output_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def write_metadata(data_path: Path, metadata: dict[str, Any]) -> None:
    """Write metadata next to a data file, e.g. x_raw.parquet -> x_raw.metadata.json."""
    metadata_path = data_path.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
