from __future__ import annotations

import sys
from pathlib import Path

from ..utils import detect_newline


def register_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "format-newlines",
        help="Ensure single newline separators between paragraphs are expanded to two.",
    )
    parser.add_argument(
        "input", type=Path, help="Path to the Markdown file to normalise."
    )
    parser.set_defaults(func=run)


def expand_single_newlines(text: str, newline: str) -> str:
    """Duplicate isolated newline separators while leaving longer runs intact."""

    if not text:
        return text

    result: list[str] = []
    i = 0
    step = len(newline)
    text_len = len(text)

    while i < text_len:
        if text.startswith(newline, i):
            count = 1
            while text.startswith(newline, i + count * step):
                count += 1

            has_prev = i > 0
            has_next = i + count * step < text_len
            prev_is_newline = i >= step and text.startswith(newline, i - step)
            next_is_newline = text.startswith(newline, i + count * step)

            if count == 1 and has_prev and has_next and not prev_is_newline and not next_is_newline:
                result.append(newline * 2)
            else:
                result.append(newline * count)

            i += count * step
            continue

        result.append(text[i])
        i += 1

    return "".join(result)


def run(args) -> int:
    if not args.input.is_file():
        sys.stderr.write(f"Input file not found: {args.input}\n")
        return 1

    text = args.input.read_text(encoding="utf-8")
    newline = detect_newline(text)
    formatted = expand_single_newlines(text, newline)

    if formatted == text:
        print("Paragraph spacing already normalised.")
        return 0

    args.input.write_text(formatted, encoding="utf-8")
    print(f"Reformatted paragraph spacing in {args.input}")
    return 0


