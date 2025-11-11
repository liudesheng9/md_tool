from __future__ import annotations

import argparse
import sys
from typing import Callable, List, Sequence, Optional

from .types import MarkdownArtifact, PipelineStageError

AUTO_OUTPUT_STAGES = {"split"}


def _split_stages(tokens: Sequence[str]) -> List[List[str]]:
    stages: List[List[str]] = []
    current: List[str] = []

    # Allow and skip initial '=' for grammar like: -i file.md = cmd ...
    iterator = iter(tokens)
    for token in iterator:
        if not stages and not current and token == "=":
            # Skip leading '='
            continue

        # Regular processing
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
    # Rewrite convenience form `split 5` in pipeline to use --parts
    # so that a positional optional 'input' defined by the tool doesn't capture '5'.
    if tokens and tokens[0] == "split":
        # tokens: ["split", "5", ...] -> ["split", "--parts", "5", ...]
        if len(tokens) >= 2 and not tokens[1].startswith("-"):
            try:
                int(tokens[1])
            except ValueError:
                pass
            else:
                tokens = [tokens[0], "--parts", tokens[1], *tokens[2:]]

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
    *,
    input_path: Optional["Path"] = None,
) -> MarkdownArtifact:
    from pathlib import Path  # local import to avoid cycles in some environments

    if input_path is None:
        raise PipelineStageError(
            "Pipeline requires a global -i/--input file before '='. Example: "
            "md-tool pipeline -i file.md = translate-md ...",
            stage=None,
        )

    if not Path(input_path).is_file():
        raise PipelineStageError(f"Input file not found: {input_path}", stage=None)

    try:
        initial_text = Path(input_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise PipelineStageError(f"Failed to read input file: {exc}", stage=None) from exc

    stages = _split_stages(raw_tokens)

    parsed_stages: List[tuple[List[str], argparse.Namespace]] = []
    for tokens in stages:
        args = _parse_stage(parser_factory, tokens)
        stage_name = getattr(args, "command", tokens[0] if tokens else "<unknown>")
        caps = getattr(args, "pipeline_caps", None)
        # Refuse stage-level input usage for tools that don't allow it
        if getattr(caps, "allow_stage_input", False) is False:
            if hasattr(args, "input") and getattr(args, "input") is not None:
                raise PipelineStageError(
                    (
                        f"Stage '{stage_name}' received a positional input path, which is not allowed in pipeline mode. "
                        f"Use: md-tool pipeline -i <file> = {stage_name} [options] ..."
                    ),
                    stage=stage_name,
                )
        parsed_stages.append((tokens, args))

    if parsed_stages:
        last_tokens, last_args = parsed_stages[-1]
        last_stage_name = getattr(last_args, "command", last_tokens[0] if last_tokens else "<unknown>")
        if last_stage_name in AUTO_OUTPUT_STAGES:
            output_value = getattr(last_args, "output", None)
            if not output_value:
                raise PipelineStageError(
                    f"The final stage '{last_stage_name}' requires -o/--output to be provided.",
                    stage=last_stage_name,
                )

    artifact: MarkdownArtifact | None = MarkdownArtifact.from_text(
        initial_text, name=str(input_path)
    )
    for index, (tokens, args) in enumerate(parsed_stages, start=1):
        stage_name = getattr(args, "command", tokens[0] if tokens else "<unknown>")
        pipeline_func = getattr(args, "pipeline_func")
        caps = getattr(args, "pipeline_caps", None)

        # Enforce input cardinality before executing the stage
        if caps is not None:
            doc_count = len(artifact.documents) if artifact and artifact.documents is not None else 0
            mode = getattr(caps, "input_mode", "single")
            if mode == "single" and doc_count != 1:
                raise PipelineStageError(
                    (
                        f"Stage '{stage_name}' requires exactly one input document at this point in the pipeline "
                        f"(received {doc_count}). Use '-i <file>' to start the pipeline and avoid splitting or combining "
                        f"into multiple documents before this stage."
                    ),
                    stage=stage_name,
                )

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

