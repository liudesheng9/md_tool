from __future__ import annotations

import argparse
import sys
from typing import List

from .combine import register_parser as register_combine
from .format_newlines import register_parser as register_format_newlines
from .split import register_parser as register_split
from .translate.text import register_parser as register_translate
from .translate.translate_md import register_parser as register_translate_md


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md-tool", description="Utility commands for working with Markdown files."
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    register_split(subparsers)
    register_combine(subparsers)
    register_format_newlines(subparsers)
    register_translate(subparsers)
    register_translate_md(subparsers)

    return parser


def parse_args(argv: List[str]) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    return args.func(args)


def cli() -> None:
    """Entry point for the console script."""

    raise SystemExit(main(sys.argv[1:]))


