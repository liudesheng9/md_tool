from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from .types import MarkdownArtifact, MarkdownDocument, PipelineStageError


class PipelineStageRunner:
    """Utility helper that encapsulates common pipeline stage bookkeeping."""

    def __init__(
        self,
        stage_name: str,
        args,
        artifact: Optional[MarkdownArtifact],
    ) -> None:
        self.stage_name = stage_name
        self.args = args
        self.artifact = artifact

    def upstream_documents(self) -> List[MarkdownDocument]:
        if self.artifact and self.artifact.documents:
            return [document.clone() for document in self.artifact.documents]
        return []

    def load_or_upstream(
        self,
        loader: Callable[[], MarkdownDocument],
    ) -> List[MarkdownDocument]:
        documents = self.upstream_documents()
        if documents:
            return documents
        return [loader()]

    def ensure_single_document(self, documents: List[MarkdownDocument], message: str) -> None:
        if len(documents) != 1:
            raise PipelineStageError(message, stage=self.stage_name)

    def write_text(self, target: Path, text: str, *, error_prefix: str) -> None:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        except OSError as exc:
            raise PipelineStageError(f"{error_prefix}: {exc}", stage=self.stage_name) from exc
