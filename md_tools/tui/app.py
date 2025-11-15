from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from textual.app import App
from textual.binding import Binding

from ..tool_manager import PipelinePayload, StagePayload, ToolManager
from ..tools import iter_tool_specs
from .constants import OUTPUT_FLAG_MAP
from .step_four import StepFourScreen
from .step_one import StepOneScreen

APP_CSS = """
Screen {
    background: $panel;
}

#step-container {
    padding: 1 2;
    height: 100%;
    width: 100%;
    border: round $accent;
    background: $surface;
    layout: vertical;
    align-vertical: top;
}

.step-title {
    text-style: bold;
    margin-bottom: 1;
}

.step-help {
    color: $text-muted;
    margin-bottom: 1;
}

.panel {
    height: 1fr;
    border: round $accent;
    padding: 1;
    background: $boost;
}

.tool-column,
.pipeline-column {
    width: 1fr;
    height: 1fr;
}

#output-file-column,
#output-path-column {
    width: 1fr;
    height: 1fr;
}

.pipeline-graph {
    margin-top: 1;
    border: round $accent;
    padding: 1;
    background: $panel;
}

.output-field {
    margin-bottom: 1;
    border: round $accent;
    padding: 1;
    background: $boost;
}

.output-field-header {
    layout: horizontal;
    align-horizontal: left;
    align-vertical: middle;
    width: 100%;
}

.output-field-spacer {
    width: 1fr;
}

.output-columns {
    height: 1fr;
    min-height: 20;
}

.output-columns > .input-column,
.output-columns > .output-column {
    height: 1fr;
}

.step-actions {
    margin-top: 1;
    padding-top: 1;
    border-top: solid $accent;
    align-horizontal: right;
}

.step-error {
    color: $error;
    min-height: 1;
}

.output-status {
    color: $text-muted;
    margin-top: 1;
}

.output-field-disabled {
    opacity: 0.75;
}
"""


def discover_markdown_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.md") if path.is_file())


@dataclass
class PipelineStageModel:
    name: str
    args: list[str]


class ToolManagerApp(App):
    """Textual application used to compose pipelines interactively."""

    CSS_PATH = None
    CSS = APP_CSS
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = Path(root).resolve()
        self.available_files: list[Path] = discover_markdown_files(self.root)
        self.selected_files: list[Path] = []
        self.pipeline: list[PipelineStageModel] = []
        self.output_overrides: dict[Path, dict[int, str]] = {}
        self.output_manual_overrides: dict[Path, set[int]] = {}
        self.output_disabled: dict[Path, set[int]] = {}
        self.output_toggle_manual: dict[Path, set[int]] = {}
        self.tool_manager = ToolManager()
        self.tool_names = sorted(spec.tool.name for spec in iter_tool_specs())

    async def on_mount(self) -> None:
        await self.push_screen(StepOneScreen())

    # ---- State management helpers ------------------------------------------------
    def set_selected_files(self, files: list[Path]) -> None:
        self.selected_files = [Path(path).resolve() for path in files]
        self.output_overrides = {}
        self.output_manual_overrides = {}
        self.output_disabled = {}
        self.output_toggle_manual = {}

    def add_stage(self, name: str, args: list[str]) -> None:
        self.pipeline.append(PipelineStageModel(name=name, args=args))
        self.ensure_output_defaults()

    def remove_stage(self, index: int) -> None:
        if 0 <= index < len(self.pipeline):
            del self.pipeline[index]
            self.ensure_output_defaults()

    def ensure_output_defaults(self) -> None:
        if not self.pipeline or not self.selected_files:
            return
        valid_indices = set(self.configurable_stage_indices())
        if not valid_indices:
            return
        self.output_overrides = {
            path: {idx: value for idx, value in mapping.items() if idx in valid_indices}
            for path, mapping in self.output_overrides.items()
            if path in self.selected_files
        }
        self.output_manual_overrides = {
            path: {idx for idx in indices if idx in valid_indices}
            for path, indices in self.output_manual_overrides.items()
            if path in self.selected_files
        }
        self.output_disabled = {
            path: {idx for idx in indices if idx in valid_indices}
            for path, indices in self.output_disabled.items()
            if path in self.selected_files
        }
        self.output_toggle_manual = {
            path: {idx for idx in indices if idx in valid_indices}
            for path, indices in self.output_toggle_manual.items()
            if path in self.selected_files
        }
        for file_path in self.selected_files:
            mapping = self.output_overrides.setdefault(file_path, {})
            manual = self.output_manual_overrides.setdefault(file_path, set())
            disabled = self.output_disabled.setdefault(file_path, set())
            toggle_manual = self.output_toggle_manual.setdefault(file_path, set())
            for idx in valid_indices:
                default_value = self._default_output_path(file_path, idx)
                if idx in manual:
                    mapping.setdefault(idx, default_value)
                else:
                    mapping[idx] = default_value
                is_final_stage = idx == len(self.pipeline) - 1
                allow_disable = not is_final_stage and self.pipeline[idx].name in OUTPUT_FLAG_MAP
                if is_final_stage:
                    disabled.discard(idx)
                    toggle_manual.discard(idx)
                    continue
                if not allow_disable:
                    disabled.discard(idx)
                    toggle_manual.discard(idx)
                    continue
                if idx not in toggle_manual:
                    disabled.add(idx)

    def _default_output_path(self, file_path: Path, stage_index: int) -> str:
        suffix = file_path.suffix or ".md"
        stem = file_path.stem
        if stage_index == len(self.pipeline) - 1:
            tag = "_out_final"
        else:
            tag = f"_out_{stage_index + 1}"
        return str(file_path.parent / f"{stem}{tag}{suffix}")

    def update_output_override(self, file_path: Path, stage_index: int, path: str) -> None:
        mapping = self.output_overrides.setdefault(file_path, {})
        mapping[stage_index] = path
        manual = self.output_manual_overrides.setdefault(file_path, set())
        manual.add(stage_index)

    def update_output_disabled(self, file_path: Path, stage_index: int, disabled: bool) -> None:
        mapping = self.output_disabled.setdefault(file_path, set())
        manual_toggles = self.output_toggle_manual.setdefault(file_path, set())
        if stage_index == len(self.pipeline) - 1:
            mapping.discard(stage_index)
            manual_toggles.discard(stage_index)
            return
        if disabled:
            mapping.add(stage_index)
        else:
            mapping.discard(stage_index)
        manual_toggles.add(stage_index)

    def stage_requires_output(self, stage_index: int) -> bool:
        if not (0 <= stage_index < len(self.pipeline)):
            return False
        stage = self.pipeline[stage_index]
        is_last = stage_index == len(self.pipeline) - 1
        return stage.name in OUTPUT_FLAG_MAP or is_last

    def configurable_stage_indices(self) -> list[int]:
        return [idx for idx in range(len(self.pipeline)) if self.stage_requires_output(idx)]

    def build_payloads(self) -> list[PipelinePayload]:
        payloads: list[PipelinePayload] = []
        for file_path in self.selected_files:
            stages: list[StagePayload] = []
            overrides = self.output_overrides.get(file_path, {})
            disabled_indices = self.output_disabled.get(file_path, set())
            for index, stage in enumerate(self.pipeline):
                args = list(stage.args)
                flag = OUTPUT_FLAG_MAP.get(stage.name)
                override_path = overrides.get(index)
                if flag and override_path and index not in disabled_indices:
                    args = apply_output_flag(args, flag, override_path)
                stages.append(StagePayload(stage.name, tuple(args)))
            payloads.append(PipelinePayload(input_path=file_path, stages=tuple(stages)))
        return payloads

    def run_selected_pipelines(self) -> str:
        payloads = self.build_payloads()
        if not payloads:
            raise RuntimeError("No payloads to execute.")
        results = self.tool_manager.run_payloads(payloads)
        return f"Executed {len(results)} pipeline(s)."

    def start_pipeline_run(self) -> None:
        if not self.pipeline or not self.selected_files:
            self.bell()
            return
        result_screen = StepFourScreen()
        self.push_screen(result_screen)
        result_screen.start_run(self.run_selected_pipelines)


def apply_output_flag(args: list[str], flag: str, path: str) -> list[str]:
    """Ensure the given output flag uses the provided path."""

    updated = list(args)
    try:
        index = updated.index(flag)
    except ValueError:
        updated.extend([flag, path])
        return updated

    if index + 1 < len(updated):
        updated[index + 1] = path
    else:
        updated.append(path)
    return updated
