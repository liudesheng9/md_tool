from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

from .types import MarkdownDocument


def default_output_name(input_file: Path, *, multiple_outputs: bool) -> str:
    suffix = input_file.suffix or ".md"
    stem = input_file.stem or input_file.name or "output"
    if multiple_outputs:
        return f"{stem}_out"
    return f"{stem}_out{suffix}"


def resolve_document_label(
    document: MarkdownDocument,
    default_base: str,
    index: int,
    suffix: str,
) -> str:
    if document.name:
        candidate = Path(document.name).name
        if candidate:
            return candidate
    return f"{default_base}_part_{index}{suffix}"
