from __future__ import annotations

from typing import Optional

from ...pipeline.types import MarkdownArtifact, MarkdownDocument, PipelineStageError
from ...utils import detect_newline


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

    result_documents: list[MarkdownDocument] = []
    for index, document in enumerate(documents, start=1):
        newline = detect_newline(document.text)
        formatted = tool.expand_single_newlines(document.text, newline)
        result_documents.append(MarkdownDocument(text=formatted, name=document.name))

        if not args.output:
            if artifact is None or not artifact.documents:
                if args.input:
                    if formatted == document.text:
                        print("Paragraph spacing already normalised.")
                    else:
                        print(f"Reformatted paragraph spacing in {args.input}")
                else:
                    label = document.name or f"document {index}"
                    if formatted == document.text:
                        print(f"Paragraph spacing already normalised for {label}.")
                    else:
                        print(f"Reformatted paragraph spacing in {label}.")
            else:
                label = document.name or f"document {index}"
                if formatted != document.text:
                    print(f"Reformatted paragraph spacing in {label}.")

    renderable = True
    if args.output:
        if len(result_documents) != 1:
            raise PipelineStageError(
                "--output can only be used when the stage produces a single document.",
                stage=stage_name,
            )
        try:
            formatted_text = result_documents[0].text
            original_text = documents[0].text
            if formatted_text == original_text:
                print("Paragraph spacing already normalised.")
            args.output.write_text(formatted_text, encoding="utf-8")
        except OSError as exc:
            raise PipelineStageError(
                f"Failed to write formatted Markdown: {exc}",
                stage=stage_name,
            ) from exc
        if result_documents[0].text == documents[0].text:
            print(f"Copied Markdown to {args.output}")
        else:
            print(f"Wrote reformatted Markdown to {args.output}")
        result_documents = [
            MarkdownDocument(text=result_documents[0].text, name=str(args.output))
        ]
        renderable = False

    return MarkdownArtifact(result_documents, renderable=renderable)

