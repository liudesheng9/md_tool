from __future__ import annotations

from typing import List, Optional

from ...pipeline.types import MarkdownArtifact, MarkdownDocument, PipelineStageError
from ...translate.text import TranslationError


def _load_document(args, stage_name: str) -> MarkdownDocument:
    if args.input is None:
        raise PipelineStageError(
            f"{stage_name} stage requires an input document when used without upstream pipeline data.",
            stage=stage_name,
        )

    if not args.input.is_file():
        raise PipelineStageError(
            f"Input file not found: {args.input}",
            stage=stage_name,
        )

    text = args.input.read_text(encoding="utf-8")
    return MarkdownDocument(text=text, name=str(args.input))


def run_stage(tool, args, artifact: Optional[MarkdownArtifact]) -> MarkdownArtifact:
    stage_name = tool.name

    if artifact is None or not artifact.documents:
        documents = [_load_document(args, stage_name)]
    else:
        documents = [doc.clone() for doc in artifact.documents]

    result_documents: List[MarkdownDocument] = []
    last_debug_records: Optional[List[dict]] = None

    for document in documents:
        try:
            translated_text, debug_records = tool.translate_document(
                document.text,
                args,
                enable_progress=True,
            )
        except (ValueError, TranslationError) as exc:
            raise PipelineStageError(str(exc), stage=stage_name) from exc
        except Exception as exc:
            raise PipelineStageError(f"Translation failed: {exc}", stage=stage_name) from exc

        result_documents.append(MarkdownDocument(text=translated_text, name=document.name))
        last_debug_records = debug_records

    if args.debug_output:
        if len(result_documents) != 1:
            raise PipelineStageError(
                "Debug output is only supported when a single document is produced in pipeline mode.",
                stage=stage_name,
            )
        try:
            tool.write_debug_output(
                args.debug_output,
                source=result_documents[0].name,
                target=str(args.output) if args.output else None,
                records=last_debug_records or [],
            )
        except OSError as exc:
            raise PipelineStageError(
                f"Failed to write debug output: {exc}",
                stage=stage_name,
            ) from exc

    renderable = True
    if args.output:
        if len(result_documents) != 1:
            raise PipelineStageError(
                "--output can only be used when a single document is produced in pipeline mode.",
                stage=stage_name,
            )
        try:
            args.output.write_text(result_documents[0].text, encoding="utf-8")
        except OSError as exc:
            raise PipelineStageError(
                f"Failed to write translated Markdown: {exc}",
                stage=stage_name,
            ) from exc
        print(f"Wrote translated Markdown to {args.output}")
        result_documents = [
            MarkdownDocument(text=result_documents[0].text, name=str(args.output))
        ]
        renderable = False

    return MarkdownArtifact(result_documents, renderable=renderable)

