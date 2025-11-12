from __future__ import annotations

import asyncio
import io
import shlex
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, ListItem, ListView, Static, Switch

try:  # Textual 0.60+ provides TextLog; fall back for older releases.
    from textual.widgets import TextLog  # type: ignore
except ImportError:  # pragma: no cover - compatibility shim
    class TextLog(VerticalScroll):
        """Minimal shim that mimics TextLog.write for older Textual releases."""

        def __init__(self, *_, id: str | None = None, classes: str | None = None, **__) -> None:
            super().__init__(id=id, classes=classes)

        def write(self, line: str) -> None:
            if not line:
                return
            self.mount(Static(line, classes="log-line"))

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
        self.output_manual_overrides: dict[Path, set[int]] = {}
        self.output_disabled: dict[Path, set[int]] = {}
        self.tool_manager = ToolManager()
        self.tool_names = sorted(spec.tool.name for spec in iter_tool_specs())

    async def on_mount(self) -> None:
        await self.push_screen(StepOneScreen())

    # ---- State management helpers ------------------------------------------------
    def set_selected_files(self, files: list[Path]) -> None:
        self.selected_files = files
        self.output_overrides = {}
        self.output_manual_overrides = {}
        self.output_disabled = {}

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
        for file_path in self.selected_files:
            mapping = self.output_overrides.setdefault(file_path, {})
            manual = self.output_manual_overrides.setdefault(file_path, set())
            disabled = self.output_disabled.setdefault(file_path, set())
            for idx in valid_indices:
                default_value = self._default_output_path(file_path, idx)
                if idx in manual:
                    mapping.setdefault(idx, default_value)
                else:
                    mapping[idx] = default_value
                if idx == len(self.pipeline) - 1 and idx in disabled:
                    disabled.remove(idx)

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
        if stage_index == len(self.pipeline) - 1:
            mapping.discard(stage_index)
            return
        if disabled:
            mapping.add(stage_index)
        else:
            mapping.discard(stage_index)

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


class StepOneScreen(Screen):
    """Screen that allows the user to pick Markdown files."""

    def __init__(self) -> None:
        super().__init__()
        self.temp_selected: set[Path] = set()

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(
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
            item = ListItem(label)
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
            item = ListItem(Static(display))
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

    class Toggled(Message):
        def __init__(self, sender: OutputField, stage_index: int, enabled: bool) -> None:
            self.stage_index = stage_index
            self.enabled = enabled
            super().__init__()

    def __init__(
        self,
        stage_index: int,
        stage_name: str,
        value: str,
        *,
        allow_disable: bool,
        enabled: bool,
    ) -> None:
        super().__init__(classes="output-field")
        self.stage_index = stage_index
        self.stage_name = stage_name
        self.value = value
        self.allow_disable = allow_disable
        self.enabled = enabled
        self._input_id = f"output-{self.stage_index}"
        self._switch_id = f"output-toggle-{self.stage_index}"
        self._body_id = f"output-body-{self.stage_index}"

    def compose(self) -> ComposeResult:
        label = Label(f"{self.stage_index + 1}. {self.stage_name}")
        if self.allow_disable:
            yield Horizontal(
                label,
                Static("Emit output"),
                Switch(
                    value=self.enabled,
                    id=self._switch_id,
                ),
            )
        else:
            yield label
        yield Vertical(id=self._body_id)

    def on_mount(self) -> None:
        self._render_body()

    def _render_body(self) -> None:
        body = self.query_one(f"#{self._body_id}", Vertical)
        for child in list(body.children):
            child.remove()
        if self.allow_disable and not self.enabled:
            body.mount(
                Static(
                    "This stage will not write an intermediate file.",
                    classes="output-disabled-message",
                )
            )
            return
        input_widget = Input(value=self.value, id=self._input_id)
        body.mount(input_widget)

    def _active_input(self) -> Input | None:
        if self.allow_disable and not self.enabled:
            return None
        try:
            return self.query_one(f"#{self._input_id}", Input)
        except Exception:
            return None

    @on(Input.Changed)
    def handle_change(self, event: Input.Changed) -> None:
        if self.allow_disable and not self.enabled:
            return
        self.value = event.value
        self.post_message(OutputField.Changed(self, self.stage_index, event.value))

    @on(Switch.Changed)
    def handle_toggle(self, event: Switch.Changed) -> None:
        if not self.allow_disable or event.switch.id != self._switch_id:
            return
        self.enabled = bool(event.value)
        self._render_body()
        input_widget = self._active_input()
        if input_widget is not None:
            input_widget.value = self.value
        self.post_message(OutputField.Toggled(self, self.stage_index, self.enabled))


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
        disabled = app.output_disabled.get(self.current_file, set())
        for idx in app.configurable_stage_indices():
            stage = app.pipeline[idx]
            allow_disable = idx != len(app.pipeline) - 1 and stage.name in OUTPUT_FLAG_MAP
            label = "Final Output" if idx == len(app.pipeline) - 1 else stage.name
            value = overrides.get(idx, app._default_output_path(self.current_file, idx))
            editor.mount(
                OutputField(
                    idx,
                    label,
                    value,
                    allow_disable=allow_disable,
                    enabled=idx not in disabled,
                )
            )

    def _build_output_file_list(self, app: ToolManagerApp) -> ListView:
        items: list[ListItem] = []
        for index, path in enumerate(app.selected_files):
            label = Static(str(path.relative_to(app.root)))
            item = ListItem(label)
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

    @on(OutputField.Toggled)
    def on_output_toggled(self, event: OutputField.Toggled) -> None:
        if not self.current_file:
            return
        app: ToolManagerApp = self.app  # type: ignore[assignment]
        app.update_output_disabled(self.current_file, event.stage_index, not event.enabled)

    @on(Button.Pressed, "#run-pipelines")
    def handle_run(self) -> None:
        app: ToolManagerApp = self.app  # type: ignore[assignment]
        if not app.pipeline or not app.selected_files:
            self.app.bell()
            return
        result_screen = StepFourScreen()
        self.app.push_screen(result_screen)

        textual_app: ToolManagerApp = self.app  # type: ignore[assignment]

        class ScreenLogWriter(io.TextIOBase):
            def __init__(self, owner: ToolManagerApp, screen: StepFourScreen) -> None:
                self._owner = owner
                self._screen = screen

            def write(self, data: str) -> int:  # pragma: no cover - Textual integration
                if not data:
                    return 0
                try:
                    self._owner.call_from_thread(self._screen.append_log, data)
                except RuntimeError:
                    return len(data)
                return len(data)

            def flush(self) -> None:  # pragma: no cover - Textual integration
                try:
                    self._owner.call_from_thread(self._screen.flush_pending_log)
                except RuntimeError:
                    pass

        log_writer = ScreenLogWriter(textual_app, result_screen)

        async def runner() -> None:
            try:
                def run_with_capture() -> str:
                    with redirect_stdout(log_writer), redirect_stderr(log_writer):
                        return app.run_selected_pipelines()

                message = await asyncio.to_thread(run_with_capture)
            except Exception as exc:  # pragma: no cover - runtime safeguard
                message = f"Pipeline failed: {exc}"
            finally:
                try:
                    log_writer.flush()
                except RuntimeError:
                    pass
            result_screen.mark_complete(message)

        asyncio.create_task(runner())

    @on(Button.Pressed, "#back-step3")
    def handle_back(self) -> None:
        self.app.pop_screen()


class StepFourScreen(Screen):
    """Final page that surfaces pipeline execution results."""

    def __init__(self, initial_message: str = "Running pipelines...") -> None:
        super().__init__()
        self.message = initial_message
        self._complete = False
        self._pending_lines: list[str] = [initial_message] if initial_message else []
        self._partial_line = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(
            Static("Step 4/4 - Pipeline execution", classes="step-title"),
            Static(
                "The selected pipelines are running. Logs and progress updates appear below.",
                classes="step-help",
            ),
            TextLog(
                id="run-log",
                classes="panel",
                highlight=False,
                markup=False,
                wrap=True,
            ),
            Button("Close", id="finish-step4", variant="primary", disabled=not self._complete),
            id="step-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._drain_pending_lines()
        finish_btn = self.query_one("#finish-step4", Button)
        finish_btn.disabled = not self._complete

    def append_log(self, text: str) -> None:
        if not text:
            return
        buffer = f"{self._partial_line}{text}"
        parts = buffer.splitlines(keepends=True)
        self._partial_line = ""
        for part in parts:
            if part.endswith(("\n", "\r")):
                self._emit_line(part.rstrip("\r\n"))
            else:
                self._partial_line += part

    def flush_pending_log(self) -> None:
        if self._partial_line:
            self._emit_line(self._partial_line)
            self._partial_line = ""

    def _emit_line(self, line: str) -> None:
        if self.is_mounted:
            log = self.query_one("#run-log", TextLog)
            log.write(line)
        else:
            self._pending_lines.append(line)

    def _drain_pending_lines(self) -> None:
        if not self._pending_lines:
            return
        log = self.query_one("#run-log", TextLog)
        for line in self._pending_lines:
            log.write(line)
        self._pending_lines.clear()

    def mark_complete(self, message: str) -> None:
        self.message = message
        if message:
            suffix = "" if message.endswith("\n") else "\n"
            self.append_log(f"{message}{suffix}")
        self.flush_pending_log()
        self._complete = True
        if self.is_mounted:
            finish_btn = self.query_one("#finish-step4", Button)
            finish_btn.disabled = False

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
