from __future__ import annotations

import sys
from pathlib import Path

from ..tools.base import MDTool
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

    def expand_single_newlines(self, text: str, newline: str) -> str:
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


tool = FormatNewlinesTool()


def register_parser(subparsers) -> None:
    tool.register(subparsers)
