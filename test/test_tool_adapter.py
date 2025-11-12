from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from md_tools.pipeline.tool_adapter import ToolAdapterCommand, _plan_output_assignments
from md_tools.pipeline.types import MarkdownArtifact, MarkdownDocument
from md_tools.tui.types import TUIResult


def test_tool_adapter_command_runs_with_tui_result(tmp_path):
    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    source = docs_root / "only.md"
    source.write_text("input", encoding="utf-8")

    executed_inputs: list[Path] = []
    stages_seen: list[list[str]] = []

    def fake_executor(stages, parser_factory, *, input_path):
        stages_seen.append(list(stages))
        executed_inputs.append(Path(input_path))
        return MarkdownArtifact.from_text("result")

    outputs: list[str] = []

    tui_result = TUIResult(
        selections=[source.resolve()],
        pipeline_tokens=["=", "format-newlines"],
        single_outputs={},
        multi_bases={},
    )

    parser_factory = lambda: None
    command = ToolAdapterCommand(
        parser_factory=parser_factory,
        executor=fake_executor,
        output_func=outputs.append,
        tui_launcher=lambda root, tokens, factory: tui_result,
    )

    args = SimpleNamespace(root=docs_root, output_dir=None)

    exit_code = command.execute(args)

    assert exit_code == 0
    assert executed_inputs == [source.resolve()]
    assert stages_seen == [["=", "format-newlines"]]
    assert (docs_root / "only_out.md").read_text(encoding="utf-8") == "result"
    assert any("Output name mapping" in line for line in outputs)


def test_tool_adapter_command_handles_multiple_files_and_overrides(tmp_path):
    docs_root = tmp_path / "docs"
    nested = docs_root / "nested"
    nested.mkdir(parents=True)
    first = docs_root / "FIRST.MD"
    second = nested / "second.md"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")

    artifacts = {
        first.resolve(): MarkdownArtifact.from_text("alpha"),
        second.resolve(): MarkdownArtifact(
            documents=[
                MarkdownDocument(text="bravo"),
                MarkdownDocument(text="charlie", name="custom_output.md"),
            ]
        ),
    }

    executed_inputs: list[Path] = []
    stages_seen: list[list[str]] = []

    def fake_executor(stages, parser_factory, *, input_path):
        stages_seen.append(list(stages))
        executed_inputs.append(Path(input_path))
        return artifacts[Path(input_path).resolve()]

    tui_result = TUIResult(
        selections=[first.resolve(), second.resolve()],
        pipeline_tokens=["=", "split", "2"],
        single_outputs={first.resolve(): "FIRST_custom.md"},
        multi_bases={second.resolve(): "second_custom"},
    )

    outputs: list[str] = []

    parser_factory = lambda: None
    command = ToolAdapterCommand(
        parser_factory=parser_factory,
        executor=fake_executor,
        output_func=outputs.append,
        tui_launcher=lambda root, tokens, factory: tui_result,
    )

    args = SimpleNamespace(root=docs_root, output_dir=None)

    exit_code = command.execute(args)

    assert exit_code == 0
    assert executed_inputs == [first.resolve(), second.resolve()]
    assert stages_seen == [["=", "split", "2"], ["=", "split", "2"]]

    first_output = docs_root / "FIRST_custom.md"
    second_output = nested / "second_custom_part_1.md"
    third_output = nested / "custom_output.md"

    assert first_output.read_text(encoding="utf-8") == "alpha"
    assert second_output.read_text(encoding="utf-8") == "bravo"
    assert third_output.read_text(encoding="utf-8") == "charlie"
    assert outputs.count("Outputs:") >= 2


def test_plan_output_assignments_respects_custom_names(tmp_path):
    input_file = (tmp_path / "note.md").resolve()
    documents = [
        MarkdownDocument(text="first chunk"),
        MarkdownDocument(text="second chunk"),
    ]
    destination = tmp_path

    assignments = _plan_output_assignments(
        input_file,
        documents,
        destination,
        single_overrides={},
        multi_overrides={input_file: "custom_base"},
    )

    assert len(assignments) == 2
    assert assignments[0].destination.name.startswith("custom_base_part_1")


def test_plan_output_assignments_single_override(tmp_path):
    input_file = (tmp_path / "doc.md").resolve()
    documents = [MarkdownDocument(text="single")]
    destination = tmp_path

    assignments = _plan_output_assignments(
        input_file,
        documents,
        destination,
        single_overrides={input_file: "custom.md"},
    )

    assert len(assignments) == 1
    assert assignments[0].destination.name == "custom.md"
