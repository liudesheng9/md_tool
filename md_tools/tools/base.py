from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

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

