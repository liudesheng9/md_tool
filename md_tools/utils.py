from __future__ import annotations

from typing import Iterable, List, Sequence


def detect_newline(text: str) -> str:
    """Detect the dominant newline sequence in the given text."""

    if "\r\n" in text:
        return "\r\n"
    if "\r" in text:
        return "\r"
    return "\n"


def normalise_paragraph_newlines(paragraphs: List[str], newline: str) -> List[str]:
    """Return paragraphs with internal newlines converted to the requested style."""

    if newline == "\n":
        return paragraphs
    return [paragraph.replace("\n", newline) for paragraph in paragraphs]


