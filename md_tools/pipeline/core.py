from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from .types import MarkdownArtifact, PipelineStageError

StageFunc = Callable[[argparse.Namespace, MarkdownArtifact], MarkdownArtifact]


class PipelineOutputSpec:
    """Base descriptor that tools can extend to declare their stage outputs."""

    def resolve(self, _args: argparse.Namespace) -> Tuple[Path, ...]:
        return ()


@dataclass(frozen=True)
class PipelineStage:
    name: str
    tokens: Tuple[str, ...]
    args: argparse.Namespace
    func: StageFunc
    caps: object | None
    outputs: Tuple[Path, ...] = ()

    @property
    def label(self) -> str:
        return " ".join(self.tokens) if self.tokens else self.name


@dataclass(frozen=True)
class PipelineDefinition:
    stages: Tuple[PipelineStage, ...]
    input_path: Path

    def __post_init__(self) -> None:
        if not self.stages:
            raise PipelineStageError("No stages were provided to the pipeline.", stage=None)

    def all_output_paths(self) -> List[Path]:
        paths: List[Path] = []
        for stage in self.stages:
            paths.extend(stage.outputs)
        return paths

    def final_output_path(self) -> Path | None:
        for stage in reversed(self.stages):
            if stage.outputs:
                return stage.outputs[-1]
        return None


AUTO_OUTPUT_STAGES = {"split"}


def _split_stages(tokens: Sequence[str]) -> List[List[str]]:
    stages: List[List[str]] = []
    current: List[str] = []

    iterator = iter(tokens)
    for token in iterator:
        if not stages and not current and token == "=":
            continue
        if token == "=":
            if not current:
                raise PipelineStageError("Encountered '=' with no preceding stage.", stage=None)
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
    if tokens and tokens[0] == "split":
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


def build_pipeline_definition(
    raw_tokens: Sequence[str],
    parser_factory: Callable[[], argparse.ArgumentParser],
    *,
    input_path: Path,
) -> PipelineDefinition:
    stages_raw = _split_stages(raw_tokens)
    parsed: List[PipelineStage] = []
    for tokens in stages_raw:
        args = _parse_stage(parser_factory, tokens)
        stage_name = getattr(args, "command", tokens[0] if tokens else "<unknown>")
        pipeline_func = getattr(args, "pipeline_func", None)
        if pipeline_func is None:
            raise PipelineStageError(
                f"Stage '{stage_name}' is missing pipeline execution support.",
                stage=stage_name,
            )
        caps = getattr(args, "pipeline_caps", None)
        if getattr(caps, "allow_stage_input", False) is False:
            if hasattr(args, "input") and getattr(args, "input") is not None:
                raise PipelineStageError(
                    (
                        f"Stage '{stage_name}' received a positional input path, which is not allowed in pipeline mode. "
                        f"Use: md-tool pipeline -i <file> = {stage_name} [options] ..."
                    ),
                    stage=stage_name,
                )

        outputs = _resolve_stage_outputs(args)
        parsed.append(
            PipelineStage(
                name=stage_name,
                tokens=tuple(tokens),
                args=args,
                func=pipeline_func,
                caps=caps,
                outputs=outputs,
            )
        )

    _validate_auto_output(parsed)
    return PipelineDefinition(tuple(parsed), input_path=Path(input_path))


def _validate_auto_output(stages: Sequence[PipelineStage]) -> None:
    if not stages:
        return
    last_stage = stages[-1]
    if last_stage.name in AUTO_OUTPUT_STAGES:
        output_value = getattr(last_stage.args, "output", None)
        if not output_value:
            raise PipelineStageError(
                f"The final stage '{last_stage.name}' requires -o/--output to be provided.",
                stage=last_stage.name,
            )


def _resolve_stage_outputs(args: argparse.Namespace) -> Tuple[Path, ...]:
    spec = getattr(args, "pipeline_output_spec", None)
    if spec is None:
        return ()
    paths = tuple(spec.resolve(args))
    return tuple(path for path in paths if isinstance(path, Path))


def run_pipeline(pipeline_definition: PipelineDefinition) -> MarkdownArtifact:
    input_path = pipeline_definition.input_path

    if not input_path.is_file():
        raise PipelineStageError(f"Input file not found: {input_path}", stage=None)

    try:
        initial_text = input_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PipelineStageError(f"Failed to read input file: {exc}", stage=None) from exc

    artifact: MarkdownArtifact | None = MarkdownArtifact.from_text(
        initial_text, name=str(input_path)
    )
    for index, stage in enumerate(pipeline_definition.stages, start=1):
        stage_name = stage.name
        pipeline_func = stage.func
        caps = stage.caps
        args = stage.args

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

        stage_label = stage.label
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

