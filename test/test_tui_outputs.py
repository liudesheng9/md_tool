from __future__ import annotations

from pathlib import Path

from md_tools.tui.app import PipelineStageModel, ToolManagerApp


def _make_app(tmp_path: Path) -> tuple[ToolManagerApp, Path]:
    root = tmp_path / "workspace"
    root.mkdir()
    input_path = root / "note.md"
    input_path.write_text("hello world", encoding="utf-8")
    app = ToolManagerApp(root)
    app.set_selected_files([input_path])
    app.pipeline = [
        PipelineStageModel("format-newlines", []),
        PipelineStageModel("combine", []),
    ]
    app.ensure_output_defaults()
    return app, input_path


def test_build_payloads_skip_disabled_outputs(tmp_path: Path) -> None:
    app, input_path = _make_app(tmp_path)
    app.update_output_disabled(input_path, 0, True)

    payloads = app.build_payloads()
    assert len(payloads) == 1
    stages = payloads[0].stages
    assert "--output" not in stages[0].args
    assert "--output" in stages[1].args


def test_update_output_disabled_keeps_final_stage(tmp_path: Path) -> None:
    app, input_path = _make_app(tmp_path)
    final_index = len(app.pipeline) - 1

    app.update_output_disabled(input_path, final_index, True)

    assert final_index not in app.output_disabled[input_path]


def test_optional_outputs_disabled_by_default(tmp_path: Path) -> None:
    app, input_path = _make_app(tmp_path)
    disabled = app.output_disabled.get(input_path, set())
    assert 0 in disabled


def test_stage_becomes_disabled_after_pipeline_extends(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    input_path = root / "note.md"
    input_path.write_text("hello world", encoding="utf-8")
    app = ToolManagerApp(root)
    app.set_selected_files([input_path])

    app.add_stage("format-newlines", [])
    assert 0 not in app.output_disabled.get(input_path, set())

    app.add_stage("combine", [])
    assert 0 in app.output_disabled.get(input_path, set())
