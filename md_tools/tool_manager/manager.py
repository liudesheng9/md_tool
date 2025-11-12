from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Mapping, Sequence

from ..cli import build_parser
from ..pipeline import (
    MarkdownArtifact,
    PipelineDefinition,
    StagePlan,
    build_pipeline_definition,
    build_pipeline_definition_from_stage_plans,
    run_pipeline,
)


class ToolManager:
    """Run Markdown pipelines under programmatic control."""

    def __init__(
        self,
        *,
        parser_factory: Callable[[], argparse.ArgumentParser] | None = None,
        executor: Callable[..., MarkdownArtifact] = run_pipeline,
    ) -> None:
        self._parser_factory = parser_factory or build_parser
        self._executor = executor

    def run(self, pipeline_definition: PipelineDefinition) -> MarkdownArtifact:
        """Execute the configured pipeline and return the resulting artifact."""

        if not pipeline_definition.input_path.is_file():
            raise FileNotFoundError(f"Pipeline input file not found: {pipeline_definition.input_path}")

        return self._executor(pipeline_definition)

    def run_many(self, pipeline_definitions: Sequence[PipelineDefinition]) -> List[MarkdownArtifact]:
        """Execute the same manager repeatedly for a collection of pipeline inputs."""

        artifacts: List[MarkdownArtifact] = []
        for pipeline_definition in pipeline_definitions:
            artifacts.append(self.run(pipeline_definition))
        return artifacts

    def run_payloads(self, payloads: Sequence[Mapping[str, Any]]) -> List[MarkdownArtifact]:
        """Execute JSON payloads (matching the CLI schema) in sequence."""

        definitions = [self.build_definition_from_payload(payload) for payload in payloads]
        return self.run_many(definitions)

    def build_definition_from_payload(self, payload: Mapping[str, Any]) -> PipelineDefinition:
        input_value = payload.get("input")
        if not input_value:
            raise ValueError("JSON payload is missing 'input'.")
        stages = payload.get("stages")
        if not isinstance(stages, Sequence) or not stages:
            raise ValueError("JSON payload must provide a non-empty 'stages' sequence.")

        tokens: List[str] = []
        for token in stages:
            if not isinstance(token, str):
                raise ValueError("Stage tokens must be strings matching CLI arguments.")
            tokens.append(token)

        return build_pipeline_definition(tokens, self._parser_factory, input_path=Path(input_value))

    def build_definition_from_stage_plans(
        self,
        stage_plans: Sequence[StagePlan],
        *,
        input_path: Path,
    ) -> PipelineDefinition:
        return build_pipeline_definition_from_stage_plans(
            stage_plans,
            self._parser_factory,
            input_path=input_path,
        )


@dataclass(frozen=True)
class SplitPlanConfig:
    """Helper structure for building the default format->split->combine plan."""

    split_parts: int
    split_output_base: Path
    split_outputs: Sequence[Path]
    final_output: Path


def default_stage_plans(config: SplitPlanConfig) -> List[StagePlan]:
    return [
        StagePlan(tokens=("format-newlines",)),
        StagePlan(tokens=("split", config.split_parts, "-o", config.split_output_base)),
        StagePlan(tokens=("combine", "--output", config.final_output)),
    ]


def build_pipeline_io_definition(
    stage_plans: Sequence[StagePlan],
    *,
    input_path: Path,
    parser_factory: Callable[[], argparse.ArgumentParser] | None = None,
) -> PipelineDefinition:
    parser = parser_factory or build_parser
    return build_pipeline_definition_from_stage_plans(
        stage_plans,
        parser,
        input_path=input_path,
    )
