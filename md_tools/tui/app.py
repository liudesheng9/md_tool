from __future__ import annotations

import argparse
import shlex
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header, Input, ListView, Static

from ..pipeline.core import _parse_stage, _split_stages
from ..pipeline.output_utils import default_output_name
from ..pipeline.types import PipelineStageError
from .steps import create_files_panel, create_outputs_panel, create_pipeline_panel
from .steps.common import StepListItem
from .types import TUIResult


class MdToolTUI(App[TUIResult]):
    """Wizard-like Textual application for selecting files and building pipelines."""

    CSS = """
    #step-container {
        height: 1fr;
        padding: 1 2;
    }

    .step-panel {
        border: heavy $accent;
        height: 1fr;
        padding: 1 2;
    }

    ListView {
        height: 1fr;
        margin-bottom: 1;
    }

    #pipeline-diagram, #output-preview {
        height: 1fr;
        border: round $accent;
        padding: 1;
        overflow: auto;
        margin-top: 1;
        margin-bottom: 1;
    }

    #outputs-columns {
        height: 1fr;
    }

    #outputs-list-pane, #outputs-editor {
        height: 1fr;
    }

    #outputs-list-pane {
        width: 45%;
    }

    #outputs-editor {
        width: 55%;
    }
    """

    TITLE = "md-tool-tui"
    BINDINGS = [
        Binding("space", "toggle_select", "Toggle selection"),
        Binding("ctrl+n", "next_step", "Next page"),
        Binding("ctrl+b", "previous_step", "Previous page"),
        Binding("ctrl+r", "run_pipeline", "Run pipeline"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        root: Path,
        initial_tokens: Sequence[str],
        *,
        parser_factory: Callable[[], "argparse.ArgumentParser"] | None = None,
    ) -> None:
        super().__init__()
        self.root = root
        self.candidates: List[Path] = []
        self.selected_indices: set[int] = set()
        self.single_overrides: Dict[Path, str] = {}
        self.multi_overrides: Dict[Path, str] = {}
        self.initial_pipeline_tokens = list(initial_tokens)
        self.parser_factory = parser_factory

        self.current_step_index = 0
        self.steps = ("files", "pipeline", "outputs")

        # UI references
        self.files_panel = None
        self.pipeline_panel = None
        self.outputs_panel = None

        self.file_list: ListView | None = None
        self.pipeline_input: Input | None = None
        self.pipeline_diagram: Static | None = None

        self.output_file_list: ListView | None = None
        self.single_output_input: Input | None = None
        self.multi_output_input: Input | None = None
        self.output_preview: Static | None = None
        self.selection_snapshot: List[Path] | None = None

    # ---- Layout -----------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="step-container"):
            self.files_panel, self.file_list = create_files_panel()
            yield self.files_panel

            default_pipeline = " ".join(self.initial_pipeline_tokens) if self.initial_pipeline_tokens else ""
            self.pipeline_panel, self.pipeline_input, self.pipeline_diagram = create_pipeline_panel(default_pipeline)
            self.pipeline_panel.display = False
            yield self.pipeline_panel

            (
                self.outputs_panel,
                self.output_file_list,
                self.single_output_input,
                self.multi_output_input,
                self.output_preview,
            ) = create_outputs_panel()
            self.outputs_panel.display = False
            yield self.outputs_panel
        yield Footer()

    # ---- Lifecycle ---------------------------------------------------------------
    def on_mount(self) -> None:
        self._reload_candidates()
        self._populate_file_list()
        if self.file_list:
            self.file_list.focus()
        self._update_pipeline_diagram()

    # ---- Event handlers ---------------------------------------------------------
    def action_toggle_select(self) -> None:
        if self._current_step() != "files" or not self.file_list:
            return
        index = self.file_list.index or 0
        if index in self.selected_indices:
            self.selected_indices.remove(index)
        else:
            self.selected_indices.add(index)
        self._refresh_file_labels()

    def action_next_step(self) -> None:
        if self._current_step() == "files":
            if not self.selected_indices:
                self.notify("Select at least one file.", severity="warning")
                return
        if self._current_step() == "pipeline":
            tokens, error = self._current_pipeline_tokens()
            if error:
                self.notify(f"Pipeline error: {error}", severity="warning")
                return
            _, stage_error = self._validate_stages(tokens)
            if stage_error:
                self.notify(f"Pipeline error: {stage_error}", severity="warning")
                return
        if self.current_step_index < len(self.steps) - 1:
            self.current_step_index += 1
            self._show_current_step()

    def action_previous_step(self) -> None:
        if self.current_step_index > 0:
            self.current_step_index -= 1
            self._show_current_step()

    def action_run_pipeline(self) -> None:
        if self._current_step() != "outputs":
            self.action_next_step()
            return
        self._submit_configuration()

    def action_cancel(self) -> None:
        raise KeyboardInterrupt()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if self._current_step() == "outputs" and event.list_view.id == "output-files":
            self._sync_output_fields()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "pipeline-input":
            self._update_pipeline_diagram()
        elif event.input.id == "single-output-input":
            self._update_single_override(event.value)
        elif event.input.id == "multi-output-input":
            self._update_multi_override(event.value)

    def on_button_pressed(self, event) -> None:
        handlers = {
            "files-next": self.action_next_step,
            "files-cancel": self.action_cancel,
            "pipeline-back": self.action_previous_step,
            "pipeline-next": self.action_next_step,
            "outputs-back": self.action_previous_step,
            "outputs-run": self.action_run_pipeline,
        }
        handler = handlers.get(getattr(event.button, "id", None))
        if handler:
            handler()

    # ---- Helpers ----------------------------------------------------------------
    def _current_step(self) -> str:
        return self.steps[self.current_step_index]

    def _show_current_step(self) -> None:
        if self.files_panel:
            self.files_panel.display = self._current_step() == "files"
        if self.pipeline_panel:
            self.pipeline_panel.display = self._current_step() == "pipeline"
        if self.outputs_panel:
            self.outputs_panel.display = self._current_step() == "outputs"
        if self._current_step() == "files":
            self.selection_snapshot = None
            self._reload_candidates()
            self._populate_file_list()
        if self._current_step() == "files" and self.file_list:
            self.file_list.focus()
        elif self._current_step() == "pipeline" and self.pipeline_input:
            self.pipeline_input.focus()
            self._update_pipeline_diagram()
        elif self._current_step() == "outputs":
            self._prepare_outputs_panel()

    def _prepare_outputs_panel(self) -> None:
        if not self.output_file_list:
            return
        self.selection_snapshot = self._selected_paths()
        try:
            self.output_file_list.clear()
        except AttributeError:
            for child in list(self.output_file_list.children):
                child.remove()
        for index, path in enumerate(self.selection_snapshot, start=1):
            label = self._format_output_label(index, path)
            self.output_file_list.append(StepListItem(label))
        if self.output_file_list.children:
            self.output_file_list.index = 0
            self._sync_output_fields()
        else:
            if self.single_output_input:
                self.single_output_input.value = ""
            if self.multi_output_input:
                self.multi_output_input.value = ""
            if self.output_preview:
                self.output_preview.update("No files selected.")
        self.output_file_list.focus()

    def _reload_candidates(self) -> None:
        self.candidates = self._discover_markdown_inputs()
        self._prune_selected_indices()

    def _prune_selected_indices(self) -> None:
        self.selected_indices = {idx for idx in self.selected_indices if idx < len(self.candidates)}

    def _discover_markdown_inputs(self) -> List[Path]:
        markdown_files: List[Path] = []
        for path in self.root.rglob("*"):
            if path.is_file() and path.suffix.lower() == ".md":
                markdown_files.append(path.resolve())
        return sorted(markdown_files)

    def _selected_paths(self) -> List[Path]:
        paths: List[Path] = []
        for idx in sorted(self.selected_indices):
            if 0 <= idx < len(self.candidates):
                paths.append(self.candidates[idx])
        return paths

    def _refresh_file_labels(self) -> None:
        if not self.file_list:
            return
        for index, child in enumerate(self.file_list.children):
            if isinstance(child, StepListItem):
                child.label_widget.update(self._format_file_label(index, self.candidates[index]))

    def _format_file_label(self, index: int, path: Path) -> str:
        try:
            display = path.relative_to(self.root)
        except ValueError:
            display = path
        marker = "●" if index in self.selected_indices else "○"
        return f"{marker} {index + 1:>3}. {display}"

    def _populate_file_list(self) -> None:
        if not self.file_list:
            return
        try:
            self.file_list.clear()
        except AttributeError:
            for child in list(self.file_list.children):
                child.remove()
        for index, path in enumerate(self.candidates):
            label = self._format_file_label(index, path)
            self.file_list.append(StepListItem(label))
        self._refresh_file_labels()

    def _format_output_label(self, index: int, path: Path) -> str:
        try:
            display = path.relative_to(self.root)
        except ValueError:
            display = path
        single = self._single_name_for(path)
        multi = f"{self._multi_base_for(path)}_part_<n>{path.suffix or '.md'}"
        return f"{index:>2}. {display} -> {single} | {multi}"

    def _current_output_focus(self) -> Path | None:
        if not self.output_file_list:
            return None
        index = self.output_file_list.index
        if index is None:
            return None
        paths = self.selection_snapshot or self._selected_paths()
        if index < 0 or index >= len(paths):
            return None
        return paths[index]

    def _sync_output_fields(self) -> None:
        path = self._current_output_focus()
        if not path:
            if self.single_output_input:
                self.single_output_input.value = ""
            if self.multi_output_input:
                self.multi_output_input.value = ""
            return
        if self.single_output_input:
            self.single_output_input.value = self._single_name_for(path)
        if self.multi_output_input:
            self.multi_output_input.value = self._multi_base_for(path)
        self._update_output_preview()

    def _single_name_for(self, path: Path) -> str:
        key = path.resolve()
        return self.single_overrides.get(key) or self._default_single_name(path)

    def _multi_base_for(self, path: Path) -> str:
        key = path.resolve()
        return self.multi_overrides.get(key) or default_output_name(path, multiple_outputs=True)

    def _default_single_name(self, path: Path) -> str:
        candidate = default_output_name(path, multiple_outputs=False)
        suffix = path.suffix or ".md"
        if candidate.endswith(suffix):
            return candidate
        return f"{candidate}{suffix}"

    def _update_single_override(self, value: str) -> None:
        path = self._current_output_focus()
        if not path:
            return
        key = path.resolve()
        normalized = value.strip()
        if normalized:
            self.single_overrides[key] = normalized
        elif key in self.single_overrides:
            del self.single_overrides[key]
        self._update_output_preview()
        self._refresh_output_labels()

    def _update_multi_override(self, value: str) -> None:
        path = self._current_output_focus()
        if not path:
            return
        key = path.resolve()
        normalized = value.strip()
        if normalized:
            self.multi_overrides[key] = normalized
        elif key in self.multi_overrides:
            del self.multi_overrides[key]
        self._update_output_preview()
        self._refresh_output_labels()

    def _current_pipeline_tokens(self) -> tuple[List[str], Optional[str]]:
        if not self.pipeline_input:
            return [], None
        raw = self.pipeline_input.value.strip()
        if not raw:
            return [], None
        try:
            tokens = shlex.split(raw)
        except ValueError as exc:
            return [], str(exc)
        return tokens, None

    def _update_pipeline_diagram(self) -> None:
        if not self.pipeline_input or not self.pipeline_diagram:
            return
        tokens, error = self._current_pipeline_tokens()
        if error:
            self.pipeline_diagram.update(f"[!] {error}")
            return
        stages, stage_error = self._validate_stages(tokens)
        if stage_error:
            self.pipeline_diagram.update(f"[!] {stage_error}")
            return
        pretty = "Pipeline schematic:\n  input -> " + " -> ".join(f"[{stage}]" for stage in stages) + " -> output"
        self.pipeline_diagram.update(pretty)

    def _update_output_preview(self) -> None:
        if not self.output_preview:
            return
        path = self._current_output_focus()
        if not path:
            self.output_preview.update("Select a file to preview names.")
            return
        suffix = path.suffix or ".md"
        single_name = self._single_name_for(path)
        multi_base = self._multi_base_for(path) or default_output_name(path, multiple_outputs=True)
        lines = [
            f"{path.name}",
            f"  Single result: {single_name}",
            f"  Multi result : {multi_base}_part_<n>{suffix}",
        ]
        self.output_preview.update("\n".join(lines))
        self._refresh_output_labels()

    def _refresh_output_labels(self) -> None:
        if not self.output_file_list:
            return
        paths = self.selection_snapshot or self._selected_paths()
        for index, child in enumerate(self.output_file_list.children):
            if isinstance(child, StepListItem) and index < len(paths):
                child.label_widget.update(self._format_output_label(index + 1, paths[index]))

    def _validate_stages(self, tokens: Sequence[str]) -> tuple[List[str], Optional[str]]:
        if not tokens:
            return [], "Provide at least one stage."
        try:
            grouped = _split_stages(tokens)
        except PipelineStageError as exc:
            return [], str(exc)

        stages: List[str] = []
        for group in grouped:
            if not group:
                return [], "Stage definitions cannot be empty."
            stages.append(" ".join(group))
            if self.parser_factory is not None:
                try:
                    _parse_stage(self.parser_factory, group.copy())
                except PipelineStageError as exc:
                    return [], str(exc)
        return stages, None

    def _submit_configuration(self) -> None:
        selections = self.selection_snapshot or self._selected_paths()
        if not selections:
            self.notify("Select at least one file.", severity="warning")
            self.current_step_index = 0
            self._show_current_step()
            return
        tokens, error = self._current_pipeline_tokens()
        if error:
            self.notify(f"Pipeline error: {error}", severity="warning")
            self.current_step_index = 1
            self._show_current_step()
            return
        stages, stage_error = self._validate_stages(tokens)
        if stage_error:
            self.notify(f"Pipeline error: {stage_error}", severity="warning")
            self.current_step_index = 1
            self._show_current_step()
            return
        result = TUIResult(
            selections=selections,
            pipeline_tokens=tokens,
            single_outputs={path: name for path, name in self.single_overrides.items()},
            multi_bases={path: base for path, base in self.multi_overrides.items()},
        )
        self.exit(result)
