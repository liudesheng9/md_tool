from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from ..paragraphs import collect_paragraphs
from ..pipeline.core import PipelineOutputSpec
from ..tools.base import MDTool
from ..tools import register_tool
from ..utils import detect_newline, normalise_paragraph_newlines


class SplitTool(MDTool):
    name = "split"
    help_text = "Split a Markdown file into multiple parts by paragraph."

    def configure_parser(self, parser) -> None:
        parser.add_argument(
            "input",
            type=Path,
            nargs="?",
            help="Path to the input Markdown file. Optional in pipeline mode when upstream data is provided.",
        )
        parser.add_argument(
            "parts",
            type=int,
            nargs="?",
            help="Number of parts to split the document into (must be >= 1)",
        )
        # Optional flag alias to support pipeline-friendly 'split 5' via token rewrite
        parser.add_argument(
            "-n",
            "--parts",
            dest="parts_flag",
            type=int,
            help="Alias for the number of parts (for pipeline usage).",
        )
        parser.add_argument(
            "-o",
            "--output",
            type=Path,
            help=(
                "Output file base name for generated parts (required). "
                "Pass the same path as the input to keep the existing location."
            ),
        )

    def run(self, args) -> int:
        parts = self.resolve_parts(args)

        if parts is None:
            sys.stderr.write("The number of parts must be provided (e.g., 'split <input> 3' or 'split --parts 3').\n")
            return 1
        if parts < 1:
            sys.stderr.write("The number of parts must be at least 1.\n")
            return 1

        if args.output is None:
            sys.stderr.write("The split command requires -o/--output to specify a file base name.\n")
            return 1

        if args.input is None:
            sys.stderr.write("Input file is required when not running in pipeline mode.\n")
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

        if parts > paragraph_count:
            sys.stderr.write(
                "Requested number of parts exceeds the number of paragraphs; refusing to split.\n"
            )
            return 1

        newline = detect_newline(text)
        grouped = self.split_paragraphs(paragraphs, parts)
        written_paths = self.write_parts(
            grouped,
            newline,
            source_path=args.input,
            output_base=args.output,
        )

        base_reference: Path = args.output
        directory = base_reference.parent if base_reference.parent != Path("") else Path(".")
        prefix = f"{base_reference.stem}_part_"

        print(f"Paragraphs found: {paragraph_count}")
        print(
            f"Wrote {len(written_paths)} file(s) to {directory} "
            f"using prefix {prefix}"
        )

        return 0

    def run_pipeline(self, args, artifact):
        from ..pipeline.split import run_stage  # noqa: WPS433

        return run_stage(self, args, artifact)

    def resolve_parts(self, args) -> Optional[int]:
        override = getattr(args, "parts_flag", None)
        if override is not None:
            return override
        return getattr(args, "parts", None)

    def pipeline_caps(self) -> MDTool.PipelineCaps:
        # Split consumes one doc and emits many docs
        return MDTool.PipelineCaps(
            allow_stage_input=False,
            input_mode="single",
            output_mode="multi",
        )

    def pipeline_output_spec(self) -> PipelineOutputSpec | None:
        return _SplitOutputSpec(self)

    def split_paragraphs(self, paragraphs: List[str], parts: int) -> List[List[str]]:
        """Split paragraphs into the requested number of parts."""

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

    def write_parts(
        self,
        parts: List[List[str]],
        newline: str,
        *,
        source_path: Path | None = None,
        output_base: Path | None = None,
    ) -> List[Path]:
        base_path = Path(output_base) if output_base else source_path
        if base_path is None:
            raise ValueError("An output base path is required to write split parts.")

        directory = base_path.parent if base_path.parent != Path("") else Path(".")
        directory.mkdir(parents=True, exist_ok=True)
        suffix = base_path.suffix or ".md"
        stem = base_path.stem or "part"
        separator = newline * 2
        written_paths: List[Path] = []

        for idx, paragraphs in enumerate(parts, start=1):
            normalised = normalise_paragraph_newlines(paragraphs, newline)
            content = separator.join(normalised)
            if content and not content.endswith(newline):
                content += newline

            target_path = directory / f"{stem}_part_{idx}{suffix}"
            target_path.write_text(content, encoding="utf-8")
            written_paths.append(target_path)

        return written_paths


tool = SplitTool()
register_tool(tool, category="document")


def register_parser(subparsers) -> None:
    tool.register(subparsers)


def _build_part_paths(base_path: Path, parts: int) -> List[Path]:
    suffix = base_path.suffix or ".md"
    stem = base_path.stem or "part"
    directory = base_path.parent if base_path.parent != Path("") else Path(".")
    return [directory / f"{stem}_part_{index}{suffix}" for index in range(1, parts + 1)]


class _SplitOutputSpec(PipelineOutputSpec):
    def __init__(self, tool: SplitTool) -> None:
        self._tool = tool

    def resolve(self, args) -> tuple[Path, ...]:
        output_base = getattr(args, "output", None)
        if output_base is None:
            return ()
        parts = self._tool.resolve_parts(args)
        if parts is None or parts < 1:
            return ()
        return tuple(_build_part_paths(output_base, parts))
