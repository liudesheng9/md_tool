from __future__ import annotations

import argparse
import sys
from typing import List

from .manpage import print_man_page
from .pipeline.command import PipelineCommand
from .pipeline.tool_adapter import ToolAdapterCommand
from .pipeline import run_pipeline as execute_pipeline
from .translate.text import register_parser as register_translate
from .tools import iter_tool_specs

# Ensure tool modules are imported so registration side-effects occur
from . import combine as _combine_module  # noqa: F401
from . import format_newlines as _format_module  # noqa: F401
from . import split as _split_module  # noqa: F401
from .translate import translate_md as _translate_md_module  # noqa: F401


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
    tui_command = ToolAdapterCommand(
        parser_factory=build_parser,
        executor=execute_pipeline,
    )
    tui_command.register(subparsers)
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
