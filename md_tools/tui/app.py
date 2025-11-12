from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

from ..tool_manager import PipelinePayload, StagePayload, ToolManager
from ..tools import iter_tool_specs

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
}

"""

OUTPUT_FLAG_MAP: dict[str, str] = {
    "split": "-o",
    "format-newlines": "--output",
    "combine": "--output",
    "translate-md": "--output",
}


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
        self.tool_manager = ToolManager()
        self.tool_names = sorted(spec.tool.name for spec in iter_tool_specs())

    async def on_mount(self) -> None:
        await self.push_screen(StepOneScreen())

    # ---- State management helpers ------------------------------------------------
    def set_selected_files(self, files: list[Path]) -> None:
        self.selected_files = files
        self.output_overrides = {}

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
        for file_path in self.selected_files:
            mapping = self.output_overrides.setdefault(file_path, {})
            for idx in valid_indices:
                mapping.setdefault(idx, self._default_output_path(file_path, idx))

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
            for index, stage in enumerate(self.pipeline):
                args = list(stage.args)
                flag = OUTPUT_FLAG_MAP.get(stage.name)
                override_path = overrides.get(index)
                if flag and override_path:
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


class StepOneScreen(Screen):
    """Screen that allows the user to pick Markdown files."""

    def __init__(self) -> None:
        super().__init__()
        self.temp_selected: set[Path] = set()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Static("Step 1/4 – Select Markdown files", classes="step-title"),
            Static("Choose one or more .md files from the provided root directory.", classes="step-help"),
            ListView(id="file-list", classes="panel"),
            Horizontal(
                Button("Cancel", id="cancel-step1"),
                Button("Next", id="next-step1", variant="primary"),
            ),
            id="step-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        app: ToolManagerApp = self.app  # type: ignore[assignment]
        self.temp_selected = set(app.selected_files)
        self.refresh_file_list()

    def refresh_file_list(self) -> None:
        app: ToolManagerApp = self.app  # type: ignore[assignment]
        list_view = self.query_one("#file-list", ListView)
        for child in list(list_view.children):
            child.remove()
        for index, path in enumerate(app.available_files):
            marker = "[x]" if path in self.temp_selected else "[ ]"
            label = Static(f"{marker} {path.relative_to(app.root)}", markup=False)
            item = ListItem(label, id=f"file-{index}")
            item.data = str(path)
            list_view.append(item)

    @on(Button.Pressed, "#next-step1")
    def handle_next(self) -> None:
        app: ToolManagerApp = self.app  # type: ignore[assignment]
        selected = list(self.temp_selected)
        if not selected:
            self.app.bell()
            return
        app.set_selected_files(selected)
        app.ensure_output_defaults()
        self.app.push_screen(StepTwoScreen())

    @on(Button.Pressed, "#cancel-step1")
    def handle_cancel(self) -> None:
        self.app.exit()

    @on(ListView.Selected, "#file-list")
    def handle_toggle(self, event: ListView.Selected) -> None:
        data = getattr(event.item, "data", None)
        if not data:
            return
        path = Path(str(data))
        if path in self.temp_selected:
            self.temp_selected.remove(path)
        else:
            self.temp_selected.add(path)
        self.refresh_file_list()


class StepTwoScreen(Screen):
    """Pipeline construction UI."""

    def _build_tool_list(self, app: ToolManagerApp) -> ListView:
        items: list[ListItem] = []
        for index, tool_name in enumerate(app.tool_names):
            static = Static(tool_name)
            list_item = ListItem(static, id=f"tool-{index}")
            list_item.data = tool_name
            items.append(list_item)
        return ListView(*items, id="tool-list", classes="panel")

    def compose(self) -> ComposeResult:
        app: ToolManagerApp = self.app  # type: ignore[assignment]
        yield Header()
        yield Vertical(
            Static("Step 2/4 – Build the pipeline", classes="step-title"),
            Static("Select a tool, optionally add arguments, then add it to the pipeline.", classes="step-help"),
            Horizontal(
                Vertical(
                    Static("Available tools"),
                    self._build_tool_list(app),
                    Input(placeholder="Arguments (e.g., --parts 3)", id="tool-args"),
                    Button("Add Stage", id="add-stage", variant="success"),
                    classes="tool-column",
                ),
                Vertical(
                    Static("Pipeline"),
                    ListView(id="pipeline-list", classes="panel"),
                    Static("", id="pipeline-graph", classes="pipeline-graph"),
                    Horizontal(
                        Button("Remove Selected", id="remove-stage"),
                        Button("Next", id="next-step2", variant="primary"),
                        Button("Back", id="back-step2"),
                    ),
                    classes="pipeline-column",
                ),
            ),
            id="step-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_pipeline_view()

    def refresh_pipeline_view(self) -> None:
        app: ToolManagerApp = self.app  # type: ignore[assignment]
        list_view = self.query_one("#pipeline-list", ListView)
        for child in list(list_view.children):
            child.remove()
        for index, stage in enumerate(app.pipeline):
            display = f"{index + 1}. {stage.name} {' '.join(stage.args)}".strip()
            item = ListItem(Static(display), id=f"pipe-{index}")
            item.data = index
            list_view.append(item)
        graph = " -> ".join(["input"] + [stage.name for stage in app.pipeline]) or "input"
        self.query_one("#pipeline-graph", Static).update(graph)

    @on(Button.Pressed, "#add-stage")
    def handle_add_stage(self) -> None:
        app: ToolManagerApp = self.app  # type: ignore[assignment]
        tool_list = self.query_one("#tool-list", ListView)
        if tool_list.index is None:
            self.app.bell()
            return
        try:
            selected_item = tool_list.children[tool_list.index]
        except (IndexError, TypeError):
            self.app.bell()
            return
        tool_name = str(getattr(selected_item, "data", ""))
        if not tool_name:
            self.app.bell()
            return
        args_field = self.query_one("#tool-args", Input)
        args = shlex.split(args_field.value.strip()) if args_field.value.strip() else []
        app.add_stage(tool_name, args)
        args_field.value = ""
        self.refresh_pipeline_view()

    @on(Button.Pressed, "#remove-stage")
    def handle_remove_stage(self) -> None:
        app: ToolManagerApp = self.app  # type: ignore[assignment]
        list_view = self.query_one("#pipeline-list", ListView)
        if list_view.index is None:
            self.app.bell()
            return
        try:
            selected_item = list_view.children[list_view.index]
        except (IndexError, TypeError):
            self.app.bell()
            return
        stage_index = int(getattr(selected_item, "data", -1))
        if stage_index == -1:
            self.app.bell()
            return
        app.remove_stage(stage_index)
        self.refresh_pipeline_view()

    @on(Button.Pressed, "#next-step2")
    def handle_next(self) -> None:
        app: ToolManagerApp = self.app  # type: ignore[assignment]
        if not app.pipeline:
            self.app.bell()
            return
        app.ensure_output_defaults()
        self.app.push_screen(StepThreeScreen())

    @on(Button.Pressed, "#back-step2")
    def handle_back(self) -> None:
        self.app.pop_screen()


class OutputField(Static):
    """Widget containing a label and editable path input."""

    class Changed(Message):
        def __init__(self, sender: OutputField, stage_index: int, path: str) -> None:
            self.stage_index = stage_index
            self.path = path
            super().__init__()

    def __init__(self, stage_index: int, stage_name: str, value: str) -> None:
        super().__init__(classes="output-field")
        self.stage_index = stage_index
        self.stage_name = stage_name
        self.value = value

    def compose(self) -> ComposeResult:
        yield Label(f"{self.stage_index + 1}. {self.stage_name}")
        yield Input(value=self.value, id=f"output-{self.stage_index}")

    @on(Input.Changed)
    def handle_change(self, event: Input.Changed) -> None:
        self.post_message(OutputField.Changed(self, self.stage_index, event.value))


class StepThreeScreen(Screen):
    """Output configuration screen."""

    def __init__(self) -> None:
        super().__init__()
        self.current_file: Path | None = None

    def compose(self) -> ComposeResult:
        app: ToolManagerApp = self.app  # type: ignore[assignment]
        yield Header()
        yield Vertical(
            Static("Step 3/4 – Configure output paths", classes="step-title"),
            Static(
                "Only tools that emit intermediate outputs need overrides. Final output is always required.",
                classes="step-help",
            ),
            Horizontal(
                Vertical(
                    Static("Inputs"),
                    self._build_output_file_list(app),
                    id="output-file-column",
                ),
                Vertical(
                    Static("Outputs"),
                    VerticalScroll(id="output-editor", classes="panel"),
                    id="output-path-column",
                ),
            ),
            Horizontal(
                Button("Run Pipelines", id="run-pipelines", variant="primary"),
                Button("Back", id="back-step3"),
            ),
            id="step-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        app: ToolManagerApp = self.app  # type: ignore[assignment]
        app.ensure_output_defaults()
        file_list = self.query_one("#output-file-list", ListView)
        if file_list.children:
            first = file_list.children[0]
            self.current_file = Path(str(getattr(first, "data", "")))
            file_list.index = 0
            self.refresh_output_fields()

    def refresh_output_fields(self) -> None:
        if not self.current_file:
            return
        app: ToolManagerApp = self.app  # type: ignore[assignment]
        editor = self.query_one("#output-editor", VerticalScroll)
        for child in list(editor.children):
            child.remove()
        overrides = app.output_overrides.get(self.current_file, {})
        for idx in app.configurable_stage_indices():
            stage = app.pipeline[idx]
            label = "Final Output" if idx == len(app.pipeline) - 1 else stage.name
            value = overrides.get(idx, app._default_output_path(self.current_file, idx))
            editor.mount(OutputField(idx, label, value))

    def _build_output_file_list(self, app: ToolManagerApp) -> ListView:
        items: list[ListItem] = []
        for index, path in enumerate(app.selected_files):
            label = Static(str(path.relative_to(app.root)))
            item = ListItem(label, id=f"out-file-{index}")
            item.data = str(path)
            items.append(item)
        return ListView(*items, id="output-file-list", classes="panel")

    @on(ListView.Highlighted, "#output-file-list")
    def on_file_selected(self, event: ListView.Highlighted) -> None:
        data = event.item.data
        if data:
            self.current_file = Path(str(data))
            self.refresh_output_fields()

    @on(OutputField.Changed)
    def on_output_changed(self, event: OutputField.Changed) -> None:
        if not self.current_file:
            return
        app: ToolManagerApp = self.app  # type: ignore[assignment]
        app.update_output_override(self.current_file, event.stage_index, event.path)

    @on(Button.Pressed, "#run-pipelines")
    def handle_run(self) -> None:
        app: ToolManagerApp = self.app  # type: ignore[assignment]
        if not app.pipeline or not app.selected_files:
            self.app.bell()
            return
        result_screen = StepFourScreen()
        self.app.push_screen(result_screen)

        async def runner() -> None:
            try:
                message = await asyncio.to_thread(app.run_selected_pipelines)
            except Exception as exc:  # pragma: no cover - runtime safeguard
                message = f"Pipeline failed: {exc}"
            result_screen.update_message(message)

        asyncio.create_task(runner())

    @on(Button.Pressed, "#back-step3")
    def handle_back(self) -> None:
        self.app.pop_screen()


class StepFourScreen(Screen):
    """Final page that surfaces pipeline execution results."""

    def __init__(self, initial_message: str = "Running pipelines...") -> None:
        super().__init__()
        self.message = initial_message
        self._pending_message: str | None = None
        self._complete = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Static("Step 4/4 – Pipeline execution", classes="step-title"),
            Static(
                "The selected pipelines are running. You can close this screen once they finish.",
                classes="step-help",
            ),
            Static(self.message, id="run-status", classes="panel"),
            Button("Close", id="finish-step4", variant="primary", disabled=not self._complete),
            id="step-container",
        )
        yield Footer()

    def update_message(self, message: str) -> None:
        self.message = message
        self._complete = True
        if self.is_mounted:
            self.query_one("#run-status", Static).update(message)
            finish_btn = self.query_one("#finish-step4", Button)
            finish_btn.disabled = False
        else:
            self._pending_message = message

    def on_mount(self) -> None:
        if self._pending_message is not None:
            message = self._pending_message
            self._pending_message = None
            self.update_message(message)

    @on(Button.Pressed, "#finish-step4")
    def handle_close(self) -> None:
        self.app.exit(self.message)


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
