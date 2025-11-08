from __future__ import annotations

from typing import Iterable, List, Sequence


def collect_paragraphs(text: str) -> List[str]:
    """Return a list of paragraphs from the provided Markdown text.

    A paragraph is defined as a block of non-blank lines separated by at least
    one blank line. Leading and trailing blank lines are ignored. Blank lines
    inside fenced code blocks (``````, ``~~~``) are preserved inside the same
    paragraph.
    """

    paragraphs: List[str] = []
    current_lines: List[str] = []
    in_fenced_block = False

    for line in text.splitlines():
        stripped = line.lstrip()

        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fenced_block = not in_fenced_block
            current_lines.append(line)
            continue

        if in_fenced_block:
            current_lines.append(line)
            continue

        if stripped:
            current_lines.append(line)
            continue

        if current_lines:
            paragraphs.append("\n".join(current_lines))
            current_lines = []

    if current_lines:
        paragraphs.append("\n".join(current_lines))

    return paragraphs


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


