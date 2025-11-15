from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from md_tools.manpage import print_man_page
from md_tools.pipeline.command import PipelineCommand
from md_tools.pipeline import run_pipeline as execute_pipeline
from md_tools.translate.text import register_parser as register_translate
from md_tools.tools import iter_tool_specs

# Ensure tool modules are imported so registration side-effects occur
from md_tools import combine as _combine_module  # noqa: F401
from md_tools import format_newlines as _format_module  # noqa: F401
from md_tools import split as _split_module  # noqa: F401
from md_tools.translate import translate_md as _translate_md_module  # noqa: F401


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md-tool", description="Utility commands for working with Markdown files."
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    for spec in iter_tool_specs():
        spec.tool.register(subparsers)

    register_translate(subparsers)
    pipeline_command = PipelineCommand(
        parser_factory=build_parser,
        executor=execute_pipeline,
    )
    pipeline_command.register(subparsers)
    _register_tui(subparsers)
    _register_man(subparsers)

    return parser


def parse_args(argv: List[str]) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    return args.func(args)


def cli() -> None:
    """Entry point for the console script."""

    raise SystemExit(main(sys.argv[1:]))


def _register_man(subparsers) -> None:
    parser = subparsers.add_parser(
        "man",
        help="Show the md-tool manual page.",
    )
    parser.set_defaults(func=_run_man_command)


def _run_man_command(_args) -> int:
    print_man_page(stream=sys.stdout)
    return 0


def _register_tui(subparsers) -> None:
    parser = subparsers.add_parser(
        "tui",
        help="Launch the interactive TUI pipeline builder.",
    )
    parser.add_argument(
        "root",
        type=Path,
        help="Root directory containing Markdown files to process.",
    )
    parser.set_defaults(func=_run_tui_command)


def _run_tui_command(args) -> int:
    from md_tools.tui import ToolManagerApp

    app = ToolManagerApp(root=args.root)
    app.run()
    return 0


if __name__ == "__main__":
    cli()
