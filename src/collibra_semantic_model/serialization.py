"""Lightweight YAML serializer for deterministic output."""

from __future__ import annotations

from typing import Any, Iterable


def dump_yaml(data: Any) -> str:
    lines: list[str] = []
    _render(data, lines, indent=0, top_level=True)
    return "\n".join(lines) + "\n"


def _render(value: Any, lines: list[str], indent: int, top_level: bool = False) -> None:
    if isinstance(value, dict):
        for key, val in value.items():
            prefix = " " * indent + f"{key}:"
            if _is_simple(val):
                lines.append(f"{prefix} {_format_scalar(val)}")
            else:
                lines.append(prefix)
                _render(val, lines, indent + 2)
    elif isinstance(value, list):
        for item in value:
            bullet = " " * indent + "-"
            if _is_simple(item):
                lines.append(f"{bullet} {_format_scalar(item)}")
            else:
                lines.append(bullet)
                _render(item, lines, indent + 2)
        if not value and top_level:
            lines.append("[]")
    else:
        lines.append(" " * indent + _format_scalar(value))


def _is_simple(value: Any) -> bool:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return True
    return False


def _format_scalar(value: Any) -> str:
    if isinstance(value, str):
        if not value:
            return "''"
        if any(ch in value for ch in "\n:\"'{}[]#") or value.strip() != value:
            return json.dumps(value)
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)
