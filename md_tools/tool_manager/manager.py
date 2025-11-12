from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Sequence

from ..cli import build_parser
from ..pipeline import MarkdownArtifact, run_pipeline

PLACEHOLDER_SPLIT_PARTS = "<split_parts>"
PLACEHOLDER_MIDDLE_OUTPUT = "<middle_output>"
PLACEHOLDER_OUTPUT = "<output>"

DEFAULT_PIPELINE_STRUCTURE: tuple[tuple[str, ...], ...] = (
    ("format-newlines",),
    ("split", PLACEHOLDER_SPLIT_PARTS, "-o", PLACEHOLDER_MIDDLE_OUTPUT),
    ("combine", "--output", PLACEHOLDER_OUTPUT),
)


@dataclass(frozen=True)
class PipelineInput:
    """Container describing how a managed pipeline should be executed."""

    input_path: Path
    output_path: Path
    middle_output_path: Path
    split_parts: int = 2
    pipeline_structure: Sequence[Sequence[str]] = DEFAULT_PIPELINE_STRUCTURE

    def __post_init__(self) -> None:
        if self.split_parts < 1:
            raise ValueError("split_parts must be at least 1.")
        if not self.pipeline_structure:
            raise ValueError("pipeline_structure must contain at least one stage.")
        for stage in self.pipeline_structure:
            if not stage:
                raise ValueError("pipeline_structure contains an empty stage definition.")

    def build_tokens(self) -> List[str]:
        """Expand the abstract pipeline structure into the CLI grammar expected by run_pipeline."""

        tokens: List[str] = []
        for stage in self.pipeline_structure:
            tokens.append("=")
            tokens.extend(self._resolve_stage_tokens(stage))
        return tokens

    def expected_split_outputs(self) -> List[Path]:
        """Return the part files that the split stage will emit for convenience/cleanup."""

        base = self.middle_output_path
        suffix = base.suffix or ".md"
        stem = base.stem or "part"
        directory = base.parent if base.parent != Path("") else Path(".")
        return [
            directory / f"{stem}_part_{index}{suffix}"
            for index in range(1, self.split_parts + 1)
        ]

    def _resolve_stage_tokens(self, stage: Sequence[str]) -> List[str]:
        resolved: List[str] = []
        for token in stage:
            if token == PLACEHOLDER_SPLIT_PARTS:
                resolved.append(str(self.split_parts))
            elif token == PLACEHOLDER_MIDDLE_OUTPUT:
                resolved.append(str(self.middle_output_path))
            elif token == PLACEHOLDER_OUTPUT:
                resolved.append(str(self.output_path))
            else:
                resolved.append(token)
        return resolved


class ToolManager:
    """Run Markdown pipelines under programmatic control."""

    def __init__(
        self,
        *,
        parser_factory: Callable[[], argparse.ArgumentParser] | None = None,
        executor: Callable[..., MarkdownArtifact] = run_pipeline,
    ) -> None:
        self._parser_factory = parser_factory or build_parser
        self._executor = executor

    def run(self, pipeline_input: PipelineInput) -> MarkdownArtifact:
        """Execute the configured pipeline and return the resulting artifact."""

        if not pipeline_input.input_path.is_file():
            raise FileNotFoundError(f"Pipeline input file not found: {pipeline_input.input_path}")

        tokens = pipeline_input.build_tokens()
        return self._executor(tokens, self._parser_factory, input_path=pipeline_input.input_path)
