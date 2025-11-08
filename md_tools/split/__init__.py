from __future__ import annotations

import sys
from pathlib import Path
from typing import List

from ..utils import collect_paragraphs, detect_newline, normalise_paragraph_newlines


def register_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "split", help="Split a Markdown file into multiple parts by paragraph."
    )
    parser.add_argument("input", type=Path, help="Path to the input Markdown file.")
    parser.add_argument(
        "parts",
        type=int,
        help="Number of parts to split the document into (must be >= 1)",
    )
    parser.set_defaults(func=run)


def split_paragraphs(paragraphs: List[str], parts: int) -> List[List[str]]:
    """Split paragraphs into the requested number of parts.

    The resulting parts keep paragraphs contiguous while aiming for a balanced
    distribution by estimated byte length.
    """

    if parts == 1:
        return [paragraphs[:]]

    paragraph_lengths = [len(p) for p in paragraphs]
    total_remaining_length = sum(paragraph_lengths)

    result: List[List[str]] = []
    index = 0

    for part_index in range(parts):
        remaining_parts = parts - part_index

        if part_index == parts - 1:
            result.append(paragraphs[index:])
            break

        target_size = total_remaining_length / remaining_parts
        current_part: List[str] = []
        current_length = 0

        while index < len(paragraphs):
            remaining_paragraphs = len(paragraphs) - index
            min_needed = remaining_parts - 1

            if current_part:
                if current_length >= target_size and remaining_paragraphs > min_needed:
                    break
                if remaining_paragraphs <= min_needed:
                    break

            current_part.append(paragraphs[index])
            current_length += paragraph_lengths[index]
            index += 1

        result.append(current_part)
        total_remaining_length -= current_length

    return result


def write_parts(parts: List[List[str]], source_path: Path, newline: str) -> None:
    directory = source_path.parent
    suffix = source_path.suffix or ".md"
    stem = source_path.stem
    separator = newline * 2

    for idx, paragraphs in enumerate(parts, start=1):
        normalised = normalise_paragraph_newlines(paragraphs, newline)
        content = separator.join(normalised)
        if content and not content.endswith(newline):
            content += newline

        target_path = directory / f"{stem}_part_{idx}{suffix}"
        target_path.write_text(content, encoding="utf-8")


def run(args) -> int:
    if args.parts < 1:
        sys.stderr.write("The number of parts must be at least 1.\n")
        return 1

    if not args.input.is_file():
        sys.stderr.write(f"Input file not found: {args.input}\n")
        return 1

    text = args.input.read_text(encoding="utf-8")
    paragraphs = collect_paragraphs(text)

    paragraph_count = len(paragraphs)
    if paragraph_count == 0:
        sys.stderr.write("The input file does not contain any paragraphs.\n")
        return 1

    if args.parts > paragraph_count:
        sys.stderr.write(
            "Requested number of parts exceeds the number of paragraphs; refusing to split.\n"
        )
        return 1

    newline = detect_newline(text)
    grouped = split_paragraphs(paragraphs, args.parts)
    write_parts(grouped, args.input, newline)

    print(f"Paragraphs found: {paragraph_count}")
    print(
        f"Wrote {args.parts} file(s) to {args.input.parent} "
        f"using prefix {args.input.stem}_part_"
    )

    return 0


