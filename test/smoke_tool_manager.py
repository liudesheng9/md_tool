from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Sequence

# Ensure the repository root is importable so md_tools can be resolved.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from md_tools.pipeline import MarkdownArtifact, PipelineDefinition
from md_tools.tool_manager import PipelinePayload, StagePayload, ToolManager

MARKERS = ["Oliver Hart", "Library of Congress"]
TRANSLATE_ARGS: tuple[str, ...] = (
    "translate-md",
    "-t",
    "zz",
    "--workers",
    "1",
    "--delay-min",
    "0",
    "--delay-max",
    "0",
    "--bulk-delay-every",
    "0",
    "--retry-count",
    "0",
)
os.environ.setdefault("MD_TOOL_FAKE_TRANSLATE", "stub")
INPUT_PATH = REPO_ROOT / "test" / "FCFS.md"
TRANSLATE_BASE_ARGS: List[str] = [str(arg) for arg in TRANSLATE_ARGS[1:]]


def cleanup(paths: Iterable[Path]) -> None:
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            continue


def slugify(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")
    return cleaned or "scenario"


Validator = Callable[[PipelineDefinition, MarkdownArtifact, str], tuple[bool, str]]
StageBuilder = Callable[["ManagerScenario", str], List[StagePayload]]
SetupFunc = Callable[["ManagerScenario", PipelineDefinition, str], Iterable[Path]]


def expect_marker_count(marker: str, minimum: int) -> Validator:
    def _validator(_pipeline_definition: PipelineDefinition, _artifact: MarkdownArtifact, text: str) -> tuple[bool, str]:
        return (
            (True, "")
            if text.count(marker) >= minimum
            else (False, f"expected at least {minimum} occurrences of '{marker}'")
        )

    return _validator


def stage_entry(stage_name: str, *args: object) -> StagePayload:
    return StagePayload(stage_name=stage_name, args=tuple(str(arg) for arg in args))


def build_format_split_segments(
    scenario: "ManagerScenario", slug: str, *, use_parts_flag: bool
) -> List[StagePayload]:
    split_base = scenario.artifact_path(slug, "split_base")
    final_output = scenario.artifact_path(slug, "final")
    if use_parts_flag:
        split_args = ["--parts", scenario.split_parts, "-o", split_base]
    else:
        split_args = [scenario.split_parts, "-o", split_base]
    return [
        stage_entry("format-newlines"),
        stage_entry("split", *split_args),
        stage_entry("combine", "--output", final_output),
    ]


def build_split_combine_format_segments(scenario: "ManagerScenario", slug: str) -> List[StagePayload]:
    split_base = scenario.artifact_path(slug, "split_base")
    final_output = scenario.artifact_path(slug, "final")
    return [
        stage_entry("split", scenario.split_parts, "-o", split_base),
        stage_entry("combine"),
        stage_entry("format-newlines", "--output", final_output),
    ]


def build_format_combine_segments(scenario: "ManagerScenario", slug: str) -> List[StagePayload]:
    final_output = scenario.artifact_path(slug, "final")
    return [
        stage_entry("format-newlines"),
        stage_entry("combine", "--output", final_output),
    ]


def build_format_writes_middle_segments(scenario: "ManagerScenario", slug: str) -> List[StagePayload]:
    middle_path = scenario.artifact_path(slug, "format_middle", scenario.middle_ext)
    final_output = scenario.artifact_path(slug, "final")
    return [
        stage_entry("format-newlines", "--output", middle_path),
        stage_entry("combine", "--output", final_output),
    ]


def build_format_translate_segments(scenario: "ManagerScenario", slug: str) -> List[StagePayload]:
    final_output = scenario.artifact_path(slug, "final")
    debug_output = scenario.artifact_path(slug, "translate_debug", ".json")
    translate_tokens = TRANSLATE_BASE_ARGS + ["--output", final_output, "--debug-output", debug_output]
    return [
        stage_entry("format-newlines"),
        stage_entry("translate-md", *translate_tokens),
    ]


def build_translate_format_segments(scenario: "ManagerScenario", slug: str) -> List[StagePayload]:
    debug_output = scenario.artifact_path(slug, "translate_debug", ".json")
    final_output = scenario.artifact_path(slug, "final")
    translate_tokens = TRANSLATE_BASE_ARGS + ["--debug-output", debug_output]
    return [
        stage_entry("translate-md", *translate_tokens),
        stage_entry("format-newlines", "--output", final_output),
    ]


def build_combine_file_list_segments(scenario: "ManagerScenario", slug: str) -> List[StagePayload]:
    file_list_path = scenario.artifact_path(slug, "file_list", ".txt")
    final_output = scenario.artifact_path(slug, "final")
    return [stage_entry("combine", "--file-list", file_list_path, "--output", final_output)]


def build_batch_format_combine_segments(scenario: "ManagerScenario", slug: str) -> List[StagePayload]:
    return build_format_combine_segments(scenario, slug)


def file_list_setup(scenario: "ManagerScenario", _pipeline_definition: PipelineDefinition, slug: str) -> Iterable[Path]:
    file_list_path = scenario.artifact_path(slug, "file_list", ".txt")
    entries = [str(INPUT_PATH), str(INPUT_PATH)]
    file_list_path.parent.mkdir(parents=True, exist_ok=True)
    file_list_path.write_text("\n".join(entries), encoding="utf-8")
    return [file_list_path]


@dataclass
class ManagerScenario:
    name: str
    plan_builder: StageBuilder
    split_parts: int = 2
    middle_ext: str = ".md"
    expect_markers: Sequence[str] | None = None
    validator: Validator | None = None
    setup: SetupFunc | None = None
    batch_size: int = 1

    def artifact_path(self, slug: str, label: str, ext: str | None = None) -> Path:
        extension = ext if ext is not None else ".md"
        return REPO_ROOT / "test" / f"smoke_tool_manager_{slug}_{label}{extension}"

    def markers(self) -> Sequence[str]:
        return self.expect_markers if self.expect_markers is not None else MARKERS

    def build_payload(self, slug: str) -> PipelinePayload:
        stages = self.plan_builder(self, slug)
        if not stages:
            raise ValueError("Scenario produced no stages.")
        return PipelinePayload(input_path=INPUT_PATH, stages=tuple(stages))


SCENARIOS: list[ManagerScenario] = [
    ManagerScenario(
        name="Format -> Split (positional) -> Combine",
        plan_builder=lambda scenario, slug: build_format_split_segments(scenario, slug, use_parts_flag=False),
    ),
    ManagerScenario(
        name="Format -> Split (--parts flag) -> Combine",
        plan_builder=lambda scenario, slug: build_format_split_segments(scenario, slug, use_parts_flag=True),
        split_parts=3,
    ),
    ManagerScenario(
        name="Split -> Combine -> Format",
        plan_builder=build_split_combine_format_segments,
    ),
    ManagerScenario(
        name="Format -> Combine (final output)",
        plan_builder=build_format_combine_segments,
    ),
    ManagerScenario(
        name="Format (writes middle) -> Combine",
        plan_builder=build_format_writes_middle_segments,
        middle_ext=".md",
    ),
    ManagerScenario(
        name="Format -> Translate (with debug)",
        plan_builder=build_format_translate_segments,
        middle_ext=".json",
        expect_markers=["[auto->zz|stub]"],
    ),
    ManagerScenario(
        name="Translate -> Format",
        plan_builder=build_translate_format_segments,
        middle_ext=".json",
        expect_markers=["[auto->zz|stub]"],
    ),
    ManagerScenario(
        name="Combine from file list",
        plan_builder=build_combine_file_list_segments,
        middle_ext=".txt",
        expect_markers=["Oliver Hart"],
        validator=expect_marker_count("Oliver Hart", 2),
        setup=file_list_setup,
    ),
    ManagerScenario(
        name="Batch format -> combine",
        plan_builder=build_batch_format_combine_segments,
        batch_size=2,
    ),
]


def stage_output_paths(pipeline_definition: PipelineDefinition) -> List[Path]:
    return pipeline_definition.all_output_paths()


def validate_scenario(
    pipeline_definition: PipelineDefinition,
    artifact: MarkdownArtifact | None,
    scenario: ManagerScenario,
) -> tuple[bool, str]:
    if artifact is None or not artifact.documents:
        return False, "pipeline did not return any documents"
    if len(artifact.documents) != 1:
        return False, "pipeline produced multiple documents; expected exactly one"

    final_output = pipeline_definition.final_output_path()
    if final_output is None or not final_output.is_file():
        return False, "final output file was not created"

    text = final_output.read_text(encoding="utf-8")
    markers = scenario.markers()
    if markers:
        missing = [marker for marker in markers if marker not in text]
        if missing:
            return False, "missing markers: " + ", ".join(missing)

    for stage in pipeline_definition.stages:
        for path in stage.outputs:
            if not path.is_file():
                return False, f"missing stage output for {stage.name}: {path}"

    if scenario.validator:
        ok, detail = scenario.validator(pipeline_definition, artifact, text)
        if not ok:
            return False, detail

    return True, "pipeline activity completed successfully"


def build_definitions(manager: ToolManager, payloads: Sequence[PipelinePayload]) -> List[PipelineDefinition]:
    return [manager.build_definition_from_payload(payload) for payload in payloads]


def run_scenario(manager: ToolManager, scenario: ManagerScenario) -> tuple[bool, str]:
    payloads: list[PipelinePayload] = []
    definitions: list[PipelineDefinition] = []
    slugs: list[str] = []

    for index in range(1, scenario.batch_size + 1):
        suffix = None if scenario.batch_size == 1 else f"batch_{index}"
        slug = slugify(scenario.name if suffix is None else f"{scenario.name}_{suffix}")
        slugs.append(slug)
        payload = scenario.build_payload(slug)
        payloads.append(payload)

    definitions = build_definitions(manager, payloads)

    cleanup_targets: List[Path] = []
    for definition in definitions:
        cleanup_targets.extend(stage_output_paths(definition))
    cleanup(cleanup_targets)

    extra_cleanup: list[Path] = []
    try:
        if scenario.setup:
            for definition, slug in zip(definitions, slugs):
                extra_cleanup.extend(scenario.setup(scenario, definition, slug))

        artifacts = manager.run_payloads(payloads)
        if scenario.batch_size == 1:
            artifact = artifacts[0]
            return validate_scenario(definitions[0], artifact, scenario)

        for index, (definition, artifact) in enumerate(zip(definitions, artifacts), start=1):
            success, detail = validate_scenario(definition, artifact, scenario)
            if not success:
                return False, f"[run {index}] {detail}"
        return True, f"completed {scenario.batch_size} batch runs"
    except Exception as exc:  # pragma: no cover
        return False, f"{exc}"
    finally:
        cleanup(cleanup_targets + extra_cleanup)


def run_smoke() -> tuple[bool, list[tuple[str, str, str]]]:
    manager = ToolManager()
    reports: list[tuple[str, str, str]] = []
    failures = 0

    for scenario in SCENARIOS:
        success, detail = run_scenario(manager, scenario)
        label = "PASS" if success else "FAIL"
        reports.append((label, scenario.name, detail))
        if not success:
            failures += 1

    return failures == 0, reports


def main() -> int:
    success, reports = run_smoke()
    print("---- Tool Manager Smoke Report ----")
    for label, name, detail in reports:
        message = f"[{label}] {name}"
        if detail:
            message += f" - {detail}"
        print(" ", message)

    if not success:
        print("At least one tool manager scenario failed.")
        return 1

    print(f"All {len(SCENARIOS)} tool manager scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
