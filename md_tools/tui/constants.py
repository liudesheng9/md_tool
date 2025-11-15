from __future__ import annotations

OUTPUT_FLAG_MAP: dict[str, str] = {
    "split": "-o",
    "format-newlines": "--output",
    "combine": "--output",
    "translate-md": "--output",
}

__all__ = ["OUTPUT_FLAG_MAP"]
