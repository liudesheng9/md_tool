from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..pipeline.core import PipelineOutputSpec
from ..pipeline.types import MarkdownArtifact, PipelineStageError


class MDTool(ABC):
    """Abstract base class for Markdown CLI tools."""

    name: str
    help_text: str

    def register(self, subparsers) -> None:
        parser = subparsers.add_parser(self.name, help=self.help_text)
        self.configure_parser(parser)
        parser.set_defaults(
            func=self.run,
            pipeline_func=self.run_pipeline,
            command=self.name,
            pipeline_caps=self.pipeline_caps(),
            pipeline_output_spec=self.pipeline_output_spec(),
        )

    @abstractmethod
    def configure_parser(self, parser) -> None:
        """Define CLI arguments for the tool."""

    @abstractmethod
    def run(self, args) -> int:
        """Execute the tool in standalone mode."""

    def run_pipeline(
        self,
        args,
        artifact: Optional[MarkdownArtifact],
    ) -> MarkdownArtifact:
        """Execute the tool as part of a pipeline."""

        raise PipelineStageError(
            f"Tool '{self.name}' does not support pipeline execution.",
            stage=self.name,
        )

    # ---- Pipeline capability metadata ----
    @dataclass(frozen=True)
    class PipelineCaps:
        # Whether the stage accepts stage-level input paths in pipeline mode
        allow_stage_input: bool = False
        # Input mode required from upstream artifact: 'single' | 'multi' | 'either'
        input_mode: str = "single"
        # Output mode produced to artifact: 'single' | 'multi' | 'same-as-input'
        output_mode: str = "single"

    def pipeline_caps(self) -> "MDTool.PipelineCaps":
        # Default for simple one-in/one-out transformers
        return MDTool.PipelineCaps(
            allow_stage_input=False,
            input_mode="single",
            output_mode="single",
        )

    def pipeline_output_spec(self) -> PipelineOutputSpec | None:
        """Return a spec describing which files this stage writes, if any."""

        return None
