from __future__ import annotations

import sys
from pathlib import Path

from ..paragraphs import collect_paragraphs_with_metadata
from ..pipeline.core import PipelineOutputSpec
from ..tools.base import MDTool
from ..tools import register_tool
from ..utils import detect_newline


class FormatNewlinesTool(MDTool):
    name = "format-newlines"
    help_text = "Ensure single newline separators between paragraphs are expanded to two."

    def configure_parser(self, parser) -> None:
        parser.add_argument(
            "input",
            type=Path,
            nargs="?",
            help="Path to the Markdown file to normalise. Optional in pipeline mode.",
        )
        parser.add_argument(
            "-o",
            "--output",
            type=Path,
            help="Path to write the formatted Markdown (required). Use the input path here for in-place updates.",
        )

    def run(self, args) -> int:
        if args.output is None:
            sys.stderr.write("The format-newlines command requires -o/--output to specify a destination file.\n")
            return 1

        if args.input is None:
            sys.stderr.write("Input file is required when not running in pipeline mode.\n")
            return 1

        if not args.input.is_file():
            sys.stderr.write(f"Input file not found: {args.input}\n")
            return 1

        text = args.input.read_text(encoding="utf-8")
        newline = detect_newline(text)
        formatted = self.expand_single_newlines(text, newline)

        target_path = args.output
        target_directory = target_path.parent if target_path.parent != Path("") else Path(".")
        target_directory.mkdir(parents=True, exist_ok=True)

        if formatted == text:
            target_path.write_text(formatted, encoding="utf-8")
            print("Paragraph spacing already normalised.")
            print(f"Copied Markdown to {target_path}")
            return 0

        target_path.write_text(formatted, encoding="utf-8")

        print(f"Wrote reformatted Markdown to {target_path}")
        return 0

    def run_pipeline(self, args, artifact):
        from ..pipeline.format_newlines import run_stage  # noqa: WPS433

        return run_stage(self, args, artifact)

    def pipeline_caps(self) -> MDTool.PipelineCaps:
        # One input, one output (structure-preserving transformer)
        return MDTool.PipelineCaps(
            allow_stage_input=False,
            input_mode="single",
            output_mode="single",
        )

    def pipeline_output_spec(self) -> PipelineOutputSpec | None:
        return _FormatNewlinesOutputSpec()

    def expand_single_newlines(self, text: str, newline: str) -> str:
        """Duplicate isolated newline separators while leaving longer runs intact."""

        if not text:
            return text

        _, metadata = collect_paragraphs_with_metadata(text, newline=newline)
        if not metadata:
            return text

        result_parts: list[str] = []
        pending_blank_lines = 0
        previous_type: str | None = None

        for entry in metadata:
            entry_type = entry["type"]
            entry_text = newline.join(entry["lines"])
            if entry_type == "blank":
                pending_blank_lines += entry["line_end"] - entry["line_start"] + 1
                continue

            if result_parts:
                if pending_blank_lines:
                    if previous_type == "text" and entry_type == "text":
                        blank_newlines = max(2, pending_blank_lines + 1)
                    else:
                        blank_newlines = pending_blank_lines + 1
                    result_parts.append(newline * blank_newlines)
                    pending_blank_lines = 0
                elif previous_type == "text" and entry_type == "text":
                    result_parts.append(newline * 2)
                else:
                    result_parts.append(newline)
            else:
                if pending_blank_lines:
                    result_parts.append(newline * pending_blank_lines)
                    pending_blank_lines = 0

            result_parts.append(entry_text)
            previous_type = entry_type
            pending_blank_lines = 0

        if pending_blank_lines:
            result_parts.append(newline * pending_blank_lines)

        return "".join(result_parts)


tool = FormatNewlinesTool()
register_tool(tool, category="transform")


def register_parser(subparsers) -> None:
    tool.register(subparsers)


class _FormatNewlinesOutputSpec(PipelineOutputSpec):
    def resolve(self, args) -> tuple[Path, ...]:
        output = getattr(args, "output", None)
        if output:
            return (output,)
        return ()
