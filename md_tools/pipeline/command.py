from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Sequence

from .core import run_pipeline as execute_pipeline
from .types import PipelineStageError


class PipelineCommand:
    """Encapsulates CLI plumbing for running Markdown pipelines."""

    def __init__(
        self,
        *,
        parser_factory: Callable[[], argparse.ArgumentParser],
        executor: Callable[[Sequence[str], Callable[[], argparse.ArgumentParser]], object] = execute_pipeline,
    ) -> None:
        self._parser_factory = parser_factory
        self._executor = executor

    def register(self, subparsers) -> None:
        parser = subparsers.add_parser(
            "pipeline",
            help="Execute a Markdown processing pipeline (stages separated by '=').",
        )
        self._configure_parser(parser)
        parser.set_defaults(func=self.execute)

    def _configure_parser(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-i",
            "--input",
            type=Path,
            required=True,
            help=(
                "Path to the initial Markdown file for the pipeline. "
                "Use '=' to chain subsequent tools, e.g. -i file.md = translate-md ..."
            ),
        )
        parser.add_argument(
            "stages",
            nargs=argparse.REMAINDER,
            help="Pipeline stages after '=' separators, e.g. = translate-md --target fr = format-newlines",
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

    def execute(self, args) -> int:
        if not args.stages:
            sys.stderr.write("No pipeline stages supplied.\n")
            return 1

        try:
            artifact = self._executor(args.stages, self._parser_factory, input_path=args.input)
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
        return 0
