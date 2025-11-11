from __future__ import annotations

from typing import List, Optional

from ...pipeline.types import MarkdownArtifact, PipelineStageError
from ...pipeline.stage_runner import PipelineStageRunner


def run_stage(tool, args, artifact: Optional[MarkdownArtifact]) -> MarkdownArtifact:
    stage_name = tool.name
    context = PipelineStageRunner(stage_name, args, artifact)
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
    upstream = context.upstream_documents()
    if upstream:
        texts.extend(document.text for document in upstream)

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
        context.write_text(
            args.output,
            combined,
            error_prefix="Failed to write combined Markdown",
        )
        print(f"Wrote combined Markdown to {args.output}")
        renderable = False

    return MarkdownArtifact.from_text(combined, name=output_name, renderable=renderable)
