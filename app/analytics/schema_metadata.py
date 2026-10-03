"""Render each dataset's schema YAML as the text guide the SQL LLM sees."""

from __future__ import annotations

from app.data_foundation.datasets import get_dataset


def render_view_schema_guide(dataset_name: str) -> str:
    spec = get_dataset(dataset_name)
    schema = spec.schema

    lines = [
        f"Approved view: {spec.view_name}",
        f"Description: {schema.get('description', '')}",
        f"Grain: {schema.get('grain', '')}",
        "",
        "Columns:",
    ]

    for column_name, metadata in spec.columns.items():
        description = metadata.get("description", "")
        lines.append(f"- {column_name} ({metadata['type']}): {description}")

    return "\n".join(lines).strip()


def render_schema_guides(dataset_names: list[str]) -> str:
    """Render guides for the datasets available to one SQL generation request."""
    return "\n\n".join(render_view_schema_guide(name) for name in dataset_names)
