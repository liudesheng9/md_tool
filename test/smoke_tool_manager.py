from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence
from pathlib import Path

# Ensure the repository root is importable so md_tools can be resolved.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from md_tools.tool_manager.manager import (
    DEFAULT_PIPELINE_STRUCTURE,
    PLACEHOLDER_MIDDLE_OUTPUT,
    PLACEHOLDER_OUTPUT,
    PLACEHOLDER_SPLIT_PARTS,
    PipelineInput,
    ToolManager,
)
from md_tools.pipeline import MarkdownArtifact

MARKERS = ["Oliver Hart", "Library of Congress"]
TRANSLATE_BASE = (
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


def cleanup(paths: Iterable[Path]) -> None:
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            continue


def slugify(name: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "_" for char in name).strip("_")
    return cleaned or "scenario"


Validator = Callable[[PipelineInput, MarkdownArtifact, str], tuple[bool, str]]
SetupFunc = Callable[[PipelineInput], Iterable[Path]]


@dataclass
class ManagerScenario:
    name: str
    structure: Sequence[Sequence[str]]
    split_parts: int = 2
    middle_ext: str = ".md"
    expect_markers: Sequence[str] | None = None
    expect_parts: bool = False
    require_middle_file: bool = False
    validator: Validator | None = None
    setup: SetupFunc | None = None

    def build_input(self) -> PipelineInput:
        scenario_slug = slugify(self.name)
        output_path = REPO_ROOT / "test" / f"smoke_tool_manager_{scenario_slug}.md"
        middle_path = REPO_ROOT / "test" / f"smoke_tool_manager_{scenario_slug}_middle{self.middle_ext}"
        return PipelineInput(
            input_path=REPO_ROOT / "test" / "FCFS.md",
            output_path=output_path,
            middle_output_path=middle_path,
            split_parts=self.split_parts,
            pipeline_structure=self.structure,
        )

    def markers(self) -> Sequence[str]:
        return self.expect_markers if self.expect_markers is not None else MARKERS


def translate_stage(*, with_output: bool, with_debug: bool) -> tuple[str, ...]:
    tokens: list[str] = list(TRANSLATE_BASE)
    if with_output:
        tokens.extend(["--output", PLACEHOLDER_OUTPUT])
    if with_debug:
        tokens.extend(["--debug-output", PLACEHOLDER_MIDDLE_OUTPUT])
    return tuple(tokens)


def expect_marker_count(marker: str, minimum: int) -> Validator:
    def _validator(_pipeline_input: PipelineInput, _artifact: MarkdownArtifact, text: str) -> tuple[bool, str]:
        return (
            (True, "")
            if text.count(marker) >= minimum
            else (False, f"expected at least {minimum} occurrences of '{marker}'")
        )

    return _validator


def file_list_setup(pipeline_input: PipelineInput) -> Iterable[Path]:
    entries = [str(pipeline_input.input_path), str(pipeline_input.input_path)]
    pipeline_input.middle_output_path.parent.mkdir(parents=True, exist_ok=True)
    pipeline_input.middle_output_path.write_text("\n".join(entries), encoding="utf-8")
    return [pipeline_input.middle_output_path]


SCENARIOS: list[ManagerScenario] = [
    ManagerScenario(
        name="Format -> Split (positional) -> Combine",
        structure=DEFAULT_PIPELINE_STRUCTURE,
        expect_parts=True,
    ),
    ManagerScenario(
        name="Format -> Split (--parts flag) -> Combine",
        structure=(
            ("format-newlines",),
            ("split", "--parts", PLACEHOLDER_SPLIT_PARTS, "-o", PLACEHOLDER_MIDDLE_OUTPUT),
            ("combine", "--output", PLACEHOLDER_OUTPUT),
        ),
        split_parts=3,
        expect_parts=True,
    ),
    ManagerScenario(
        name="Split -> Combine -> Format",
        structure=(
            ("split", PLACEHOLDER_SPLIT_PARTS, "-o", PLACEHOLDER_MIDDLE_OUTPUT),
            ("combine",),
            ("format-newlines", "--output", PLACEHOLDER_OUTPUT),
        ),
        expect_parts=True,
    ),
    ManagerScenario(
        name="Format -> Combine (final output)",
        structure=(
            ("format-newlines",),
            ("combine", "--output", PLACEHOLDER_OUTPUT),
        ),
    ),
    ManagerScenario(
        name="Format (writes middle) -> Combine",
        structure=(
            ("format-newlines", "--output", PLACEHOLDER_MIDDLE_OUTPUT),
            ("combine", "--output", PLACEHOLDER_OUTPUT),
        ),
        require_middle_file=True,
    ),
    ManagerScenario(
        name="Format -> Translate (with debug)",
        structure=(
            ("format-newlines",),
            translate_stage(with_output=True, with_debug=True),
        ),
        middle_ext=".json",
        expect_markers=["[auto->zz|stub]"],
        require_middle_file=True,
    ),
    ManagerScenario(
        name="Translate -> Format",
        structure=(
            translate_stage(with_output=False, with_debug=True),
            ("format-newlines", "--output", PLACEHOLDER_OUTPUT),
        ),
        middle_ext=".json",
        expect_markers=["[auto->zz|stub]"],
        require_middle_file=True,
    ),
    ManagerScenario(
        name="Combine from file list",
        structure=(
            ("combine", "--file-list", PLACEHOLDER_MIDDLE_OUTPUT, "--output", PLACEHOLDER_OUTPUT),
        ),
        middle_ext=".txt",
        expect_markers=["Oliver Hart"],
        setup=file_list_setup,
        validator=expect_marker_count("Oliver Hart", 2),
    ),
]


def validate_scenario(
    pipeline_input: PipelineInput,
    artifact: MarkdownArtifact | None,
    scenario: ManagerScenario,
) -> tuple[bool, str]:
    if artifact is None or not artifact.documents:
        return False, "pipeline did not return any documents"
    if len(artifact.documents) != 1:
        return False, "pipeline produced multiple documents; expected exactly one"

    output_path = pipeline_input.output_path
    if not output_path.is_file():
        return False, "final output file was not created"
    text = output_path.read_text(encoding="utf-8")

    markers = scenario.markers()
    if markers:
        missing = [marker for marker in markers if marker not in text]
        if missing:
            return False, "missing markers: " + ", ".join(missing)

    if scenario.expect_parts:
        missing_parts = [
            str(path)
            for path in pipeline_input.expected_split_outputs()
            if not path.is_file()
        ]
        if missing_parts:
            return False, "missing split parts: " + ", ".join(missing_parts)

    if scenario.require_middle_file and not pipeline_input.middle_output_path.is_file():
        return False, f"expected middle output at {pipeline_input.middle_output_path}"

    if scenario.validator:
        ok, detail = scenario.validator(pipeline_input, artifact, text)
        if not ok:
            return False, detail

    return True, "pipeline activity completed successfully"


def run_scenario(manager: ToolManager, scenario: ManagerScenario) -> tuple[bool, str]:
    pipeline_input = scenario.build_input()
    cleanup_targets = [
        pipeline_input.output_path,
        pipeline_input.middle_output_path,
    ]
    if scenario.expect_parts:
        cleanup_targets.extend(pipeline_input.expected_split_outputs())
    cleanup(cleanup_targets)

    extra_cleanup: list[Path] = []
    try:
        if scenario.setup:
            generated = list(scenario.setup(pipeline_input))
            extra_cleanup.extend(generated)
        artifact = manager.run(pipeline_input)
        return validate_scenario(pipeline_input, artifact, scenario)
    except Exception as exc:  # pragma: no cover - defensive
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
