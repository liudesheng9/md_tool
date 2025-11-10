from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class MarkdownDocument:
    """Container for a single Markdown document passed between pipeline stages."""

    text: str
    name: Optional[str] = None

    def clone(self) -> "MarkdownDocument":
        return MarkdownDocument(text=self.text, name=self.name)


@dataclass(frozen=True)
class MarkdownArtifact:
    """Pipeline payload containing one or more Markdown documents."""

    documents: List[MarkdownDocument] = field(default_factory=list)
    renderable: bool = True

    @classmethod
    def from_text(
        cls,
        text: str,
        name: Optional[str] = None,
        *,
        renderable: bool = True,
    ) -> "MarkdownArtifact":
        return cls([MarkdownDocument(text=text, name=name)], renderable=renderable)

    def clone(self) -> "MarkdownArtifact":
        return MarkdownArtifact(
            [document.clone() for document in self.documents],
            renderable=self.renderable,
        )


class PipelineStageError(RuntimeError):
    """Raised when a pipeline stage encounters an unrecoverable error."""

    def __init__(self, message: str, stage: Optional[str] = None) -> None:
        self.stage = stage
        super().__init__(message)

