from __future__ import annotations

import argparse
import sys
from typing import Callable, List, Sequence

from .types import MarkdownArtifact, PipelineStageError


def _split_stages(tokens: Sequence[str]) -> List[List[str]]:
    stages: List[List[str]] = []
    current: List[str] = []

    for token in tokens:
        if token == "=":
            if not current:
                raise PipelineStageError(
                    "Encountered '=' with no preceding stage.",
                    stage=None,
                )
            stages.append(current)
            current = []
        else:
            current.append(token)

    if current:
        stages.append(current)

    if not stages:
        raise PipelineStageError("No stages were provided to the pipeline.", stage=None)

    return stages


def _parse_stage(
    parser_factory: Callable[[], argparse.ArgumentParser],
    tokens: Sequence[str],
) -> argparse.Namespace:
    parser = parser_factory()
    try:
        args = parser.parse_args(tokens)
    except SystemExit as exc:
        stage_name = tokens[0] if tokens else "<unknown>"
        raise PipelineStageError(
            f"Failed to parse arguments for stage '{stage_name}'.",
            stage=stage_name,
        ) from exc

    pipeline_func = getattr(args, "pipeline_func", None)
    if pipeline_func is None:
        stage_name = getattr(args, "command", tokens[0] if tokens else "<unknown>")
        raise PipelineStageError(
            f"Command '{stage_name}' does not support pipeline execution.",
            stage=stage_name,
        )

    return args


def run_pipeline(
    raw_tokens: Sequence[str],
    parser_factory: Callable[[], argparse.ArgumentParser],
) -> MarkdownArtifact:
    stages = _split_stages(raw_tokens)

    parsed_stages: List[tuple[List[str], argparse.Namespace]] = []
    for tokens in stages:
        args = _parse_stage(parser_factory, tokens)
        parsed_stages.append((tokens, args))

    artifact: MarkdownArtifact | None = None
    for index, (tokens, args) in enumerate(parsed_stages, start=1):
        stage_name = getattr(args, "command", tokens[0] if tokens else "<unknown>")
        pipeline_func = getattr(args, "pipeline_func")

        stage_label = " ".join(tokens) if tokens else stage_name
        sys.stderr.write(f"Conducting {stage_name} (tool) [stage {index}]: {stage_label}\n")
        sys.stderr.flush()

        try:
            artifact = pipeline_func(args, artifact)
        except PipelineStageError as exc:
            if exc.stage is None:
                raise
            raise exc
        except Exception as exc:
            raise PipelineStageError(
                f"Stage '{stage_name}' failed: {exc}",
                stage=stage_name,
            ) from exc

        if not isinstance(artifact, MarkdownArtifact):
            raise PipelineStageError(
                f"Stage '{stage_name}' did not return a MarkdownArtifact.",
                stage=stage_name,
            )

    return artifact or MarkdownArtifact([])


def render_artifact(artifact: MarkdownArtifact, stream = sys.stdout) -> None:
    if not artifact.renderable:
        return

    documents = artifact.documents

    if not documents:
        stream.write("")
        return

    if len(documents) == 1:
        stream.write(documents[0].text)
        if not documents[0].text.endswith(("\n", "\r")):
            stream.write("\n")
        return

    for index, document in enumerate(documents, start=1):
        if index > 1:
            stream.write("\n")
        title = document.name or f"Document {index}"
        stream.write(f"--- {title} ---\n")
        stream.write(document.text)
        if not document.text.endswith(("\n", "\r")):
            stream.write("\n")

