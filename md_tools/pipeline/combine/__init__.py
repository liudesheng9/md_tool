from __future__ import annotations

from typing import List, Optional

from ...pipeline.types import MarkdownArtifact, PipelineStageError


def run_stage(tool, args, artifact: Optional[MarkdownArtifact]) -> MarkdownArtifact:
    stage_name = tool.name
    allow_empty = artifact is not None

    try:
        inputs = tool.gather_inputs(args)
    except FileNotFoundError as exc:
        raise PipelineStageError(str(exc), stage=stage_name) from exc

    if not inputs:
        if not allow_empty:
            raise PipelineStageError(
                "No input files specified for combine stage.",
                stage=stage_name,
            )
        file_contents: List[str] = []
    else:
        try:
            tool.validate_inputs(inputs)
        except FileNotFoundError as exc:
            raise PipelineStageError(str(exc), stage=stage_name) from exc
        file_contents = tool.read_files(inputs)

    texts: List[str] = []
    if artifact is not None:
        texts.extend(document.text for document in artifact.documents)

    texts.extend(file_contents)

    if not texts:
        raise PipelineStageError(
            "Combine stage received no content to merge.",
            stage=stage_name,
        )

    combined = tool.combine_contents(texts)
    output_name = str(args.output) if args.output else None

    renderable = True
    if args.output:
        try:
            args.output.write_text(combined, encoding="utf-8")
        except OSError as exc:
            raise PipelineStageError(
                f"Failed to write combined Markdown: {exc}",
                stage=stage_name,
            ) from exc
        print(f"Wrote combined Markdown to {args.output}")
        renderable = False

    return MarkdownArtifact.from_text(combined, name=output_name, renderable=renderable)

