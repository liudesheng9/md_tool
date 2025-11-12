from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence, Union

from ..cli import build_parser
from ..pipeline import MarkdownArtifact, PipelineDefinition, build_pipeline_definition, run_pipeline


@dataclass(frozen=True)
class StagePayload:
    stage_name: str
    args: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> "StagePayload":
        stage_name = mapping.get("stage_name")
        if not isinstance(stage_name, str) or not stage_name:
            raise ValueError("Each stage entry must include a non-empty 'stage_name'.")

        raw_args = mapping.get("args", [])
        if raw_args is None:
            raw_args = []
        if not isinstance(raw_args, Iterable):
            raise ValueError("Stage 'args' must be an array of strings.")

        args = tuple(str(arg) for arg in raw_args)
        return cls(stage_name=stage_name, args=args)


@dataclass(frozen=True)
class PipelinePayload:
    input_path: Path
    stages: tuple[StagePayload, ...]

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> "PipelinePayload":
        input_value = mapping.get("input")
        if not input_value:
            raise ValueError("JSON payload is missing 'input'.")
        input_path = Path(str(input_value))

        raw_stages = mapping.get("stages")
        if not isinstance(raw_stages, Iterable):
            raise ValueError("JSON payload must provide a 'stages' array.")

        stages = tuple(StagePayload.from_mapping(stage) for stage in raw_stages)
        if not stages:
            raise ValueError("JSON payload must provide at least one stage.")

        return cls(input_path=input_path, stages=stages)


PipelinePayloadLike = Union[PipelinePayload, Mapping[str, object]]


class ToolManager:
    """Run Markdown pipelines from JSON payloads."""

    def __init__(
        self,
        *,
        parser_factory: Callable[[], argparse.ArgumentParser] | None = None,
        executor: Callable[..., MarkdownArtifact] = run_pipeline,
    ) -> None:
        self._parser_factory = parser_factory or build_parser
        self._executor = executor

    def run_payloads(self, payloads: Sequence[PipelinePayloadLike]) -> list[MarkdownArtifact]:
        normalized = [self._ensure_payload(payload) for payload in payloads]
        definitions = [self.build_definition_from_payload(payload) for payload in normalized]
        artifacts: list[MarkdownArtifact] = []
        for definition in definitions:
            if not definition.input_path.is_file():
                raise FileNotFoundError(f"Pipeline input file not found: {definition.input_path}")
            artifacts.append(self._executor(definition))
        return artifacts

    def build_definition_from_payload(self, payload: PipelinePayloadLike) -> PipelineDefinition:
        actual_payload = self._ensure_payload(payload)

        tokens: list[str] = []
        for stage in actual_payload.stages:
            tokens.append("=")
            tokens.append(stage.stage_name)
            tokens.extend(stage.args)

        return build_pipeline_definition(tokens, self._parser_factory, input_path=actual_payload.input_path)

    @staticmethod
    def _ensure_payload(payload: PipelinePayloadLike) -> PipelinePayload:
        if isinstance(payload, PipelinePayload):
            return payload
        if isinstance(payload, Mapping):
            return PipelinePayload.from_mapping(payload)
        raise TypeError("Payloads must be PipelinePayload instances or JSON-like mappings.")
