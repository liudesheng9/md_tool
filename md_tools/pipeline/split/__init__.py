from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from ...pipeline.types import MarkdownArtifact, MarkdownDocument, PipelineStageError
from ...pipeline.stage_runner import PipelineStageRunner
from ...utils import collect_paragraphs, detect_newline, normalise_paragraph_newlines


def _load_document(args, stage_name: str) -> Tuple[MarkdownDocument, Optional[Path]]:
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
    document = MarkdownDocument(text=text, name=str(args.input))
    return document, Path(args.input)


def _build_part_name(base_name: Optional[str], index: int) -> str:
    if base_name:
        path = Path(base_name)
        suffix = path.suffix or ".md"
        stem = path.stem or "part"
        return f"{stem}_part_{index}{suffix}"
    return f"part_{index}.md"


def _split_document(tool, document: MarkdownDocument, parts: int, stage_name: str) -> Tuple[List[MarkdownDocument], List[List[str]], str, int]:
    paragraphs = collect_paragraphs(document.text)
    paragraph_count = len(paragraphs)

    if paragraph_count == 0:
        raise PipelineStageError(
            "The document does not contain any paragraphs to split.",
            stage=stage_name,
        )

    if parts > paragraph_count:
        raise PipelineStageError(
            "Requested number of parts exceeds the number of paragraphs; refusing to split.",
            stage=stage_name,
        )

    newline = detect_newline(document.text)
    grouped = tool.split_paragraphs(paragraphs, parts)

    documents: List[MarkdownDocument] = []
    separator = newline * 2
    for idx, chunk in enumerate(grouped, start=1):
        normalised = normalise_paragraph_newlines(chunk, newline)
        content = separator.join(normalised)
        if content and not content.endswith(newline):
            content += newline
        part_name = _build_part_name(document.name, idx)
        documents.append(MarkdownDocument(text=content, name=part_name))

    return documents, grouped, newline, paragraph_count


def run_stage(tool, args, artifact: Optional[MarkdownArtifact]) -> MarkdownArtifact:
    stage_name = tool.name
    context = PipelineStageRunner(stage_name, args, artifact)

    parts = tool.resolve_parts(args)
    if parts is None or parts < 1:
        if parts is None:
            raise PipelineStageError("The number of parts must be provided.", stage=stage_name)
        raise PipelineStageError("The number of parts must be at least 1.", stage=stage_name)

    if artifact is None or not artifact.documents:
        document, _ = _load_document(args, stage_name)
        documents = [document]
    else:
        documents = context.upstream_documents()

    if args.output:
        context.ensure_single_document(
            documents,
            "-o/--output can only be used when the split stage receives a single document.",
        )

    result_documents: List[MarkdownDocument] = []
    for document in documents:
        split_docs, grouped, newline, paragraph_count = _split_document(tool, document, parts, stage_name)
        result_documents.extend(split_docs)

        if args.output:
            output_base = Path(args.output)
            tool.write_parts(
                grouped,
                newline,
                output_base=output_base,
            )
            print(f"Paragraphs found: {paragraph_count}")
            print(
                f"Wrote {len(split_docs)} file(s) to {output_base.parent} "
                f"using prefix {output_base.stem}_part_"
            )
        else:
            label = document.name or "document"
            print(f"Split {label} into {len(split_docs)} part(s); files not written (pipeline mode).")

    return MarkdownArtifact(result_documents, renderable=True)
