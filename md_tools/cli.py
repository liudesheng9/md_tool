from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from .combine import tool as combine_tool
from .format_newlines import tool as format_newlines_tool
from .pipeline import render_artifact, run_pipeline as execute_pipeline, PipelineStageError
from .split import tool as split_tool
from .translate.text import register_parser as register_translate
from .translate.translate_md import tool as translate_md_tool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md-tool", description="Utility commands for working with Markdown files."
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    for tool in (
        split_tool,
        combine_tool,
        format_newlines_tool,
        translate_md_tool,
    ):
        tool.register(subparsers)

    register_translate(subparsers)
    _register_pipeline(subparsers)

    return parser


def parse_args(argv: List[str]) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    return args.func(args)


def cli() -> None:
    """Entry point for the console script."""

    raise SystemExit(main(sys.argv[1:]))


def _register_pipeline(subparsers) -> None:
    parser = subparsers.add_parser(
        "pipeline",
        help="Execute a Markdown processing pipeline (stages separated by '=').",
    )
    parser.add_argument(
        "stages",
        nargs=argparse.REMAINDER,
        help="Pipeline expression, e.g. translate-md input.md --target fr = format-newlines",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write the final pipeline result to this Markdown file.",
    )
    parser.add_argument(
        "--no-output",
        action="store_true",
        help="Suppress printing the final pipeline result to stdout.",
    )
    parser.set_defaults(func=_run_pipeline_command)


def _run_pipeline_command(args) -> int:
    if not args.stages:
        sys.stderr.write("No pipeline stages supplied.\n")
        return 1

    try:
        artifact = execute_pipeline(args.stages, build_parser)
    except PipelineStageError as exc:
        prefix = f"[{exc.stage}] " if exc.stage else ""
        sys.stderr.write(f"{prefix}{exc}\n")
        return 1

    if args.output:
        documents = artifact.documents
        if not documents:
            sys.stderr.write("Pipeline produced no documents to write.\n")
            return 1
        if len(documents) != 1:
            sys.stderr.write(
                "Pipeline produced multiple documents; cannot write to a single output path.\n"
            )
            return 1
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(documents[0].text, encoding="utf-8")
        except OSError as exc:
            sys.stderr.write(f"Failed to write pipeline output: {exc}\n")
            return 1
        print(f"Wrote pipeline result to {args.output}")
    elif not args.no_output and artifact.renderable:
        render_artifact(artifact, stream=sys.stdout)

    return 0


