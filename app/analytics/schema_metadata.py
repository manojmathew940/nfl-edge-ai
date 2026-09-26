"""Load each dataset's schema YAML and render it as the text guide the SQL LLM sees."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.data_foundation.datasets import DatasetSpec, get_dataset


class SchemaMetadataError(RuntimeError):
    """Raised when analytics schema metadata cannot be loaded."""


def _load_schema_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SchemaMetadataError(f"Missing schema metadata file: {path}")

    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict):
        raise SchemaMetadataError(f"Schema metadata file is invalid: {path}")

    return payload


def _validate_schema_metadata(schema: dict[str, Any], view_name: str) -> None:
    if schema.get("view") != view_name:
        raise SchemaMetadataError(f"Schema metadata must define view: {view_name}")

    columns = schema.get("columns")
    if not isinstance(columns, dict) or not columns:
        raise SchemaMetadataError(f"Schema metadata for {view_name} has no columns.")

    for column_name, metadata in columns.items():
        if not isinstance(metadata, dict):
            raise SchemaMetadataError(
                f"Schema metadata for {view_name}.{column_name} is invalid."
            )


def _load_validated_schema_metadata(
    spec: DatasetSpec, path: Path | None = None
) -> dict[str, Any]:
    schema = _load_schema_metadata(path or spec.schema_path)
    _validate_schema_metadata(schema, spec.view_name)
    return schema


def render_view_schema_guide(dataset_name: str) -> str:
    spec = get_dataset(dataset_name)
    schema = _load_validated_schema_metadata(spec)
    description = schema.get("description", "")
    grain = schema.get("grain", "")
    columns = schema["columns"]

    lines = [
        f"Approved view: {spec.view_name}",
        f"Description: {description}",
        f"Grain: {grain}",
        "",
        "Columns:",
    ]

    for column_name, metadata in columns.items():
        column_type = metadata.get("type", "unknown")
        description = metadata.get("description", "")
        lines.append(f"- {column_name} ({column_type}): {description}")

    return "\n".join(lines).strip()


def render_schema_guides(dataset_names: list[str]) -> str:
    """Render guides for the datasets available to one SQL generation request."""
    return "\n\n".join(render_view_schema_guide(name) for name in dataset_names)
