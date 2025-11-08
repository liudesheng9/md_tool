from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, List, Sequence

from ..utils import detect_newline


def register_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "combine",
        help="Concatenate Markdown files, separating each file with a single newline.",
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="Markdown files to concatenate (ignored when --file-list is provided).",
    )
    parser.add_argument(
        "-l",
        "--file-list",
        type=Path,
        help="Path to a text file containing one Markdown path per line.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Destination Markdown file.",
    )
    parser.set_defaults(func=run)


def load_file_list(file_list: Path) -> List[Path]:
    if not file_list.is_file():
        raise FileNotFoundError(f"File list not found: {file_list}")

    lines = file_list.read_text(encoding="utf-8").splitlines()
    paths = [Path(line.strip()) for line in lines if line.strip()]
    return paths


def validate_inputs(paths: Sequence[Path]) -> None:
    missing = [path for path in paths if not path.is_file()]
    if missing:
        missing_str = "\n".join(f"  - {path}" for path in missing)
        raise FileNotFoundError(f"The following input files were not found:\n{missing_str}")


def read_files(paths: Iterable[Path]) -> List[str]:
    contents: List[str] = []
    for path in paths:
        contents.append(path.read_text(encoding="utf-8"))
    return contents


def combine_contents(contents: List[str]) -> str:
    if not contents:
        return ""

    first_text = contents[0]
    newline = detect_newline(first_text) if first_text else "\n"
    segments = [first_text.rstrip("\r\n")]

    for text in contents[1:]:
        segments.append(text.rstrip("\r\n"))

    return f"{newline}".join(segments) + newline


def run(args) -> int:
    try:
        if args.file_list:
            inputs = load_file_list(args.file_list)
        else:
            inputs = list(args.inputs)
    except FileNotFoundError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    if not inputs:
        sys.stderr.write("No input files specified.\n")
        return 1

    try:
        validate_inputs(inputs)
    except FileNotFoundError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    contents = read_files(inputs)
    combined = combine_contents(contents)
    args.output.write_text(combined, encoding="utf-8")
    print(f"Wrote combined Markdown to {args.output}")
    return 0


