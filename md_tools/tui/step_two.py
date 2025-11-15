from __future__ import annotations

import shlex
from typing import TYPE_CHECKING

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, ListItem, ListView, Static

from .step_three import StepThreeScreen

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .app import ToolManagerApp


class StepTwoScreen(Screen):
    """Pipeline construction UI."""

    def _build_tool_list(self, app: "ToolManagerApp") -> ListView:
        items: list[ListItem] = []
        for index, tool_name in enumerate(app.tool_names):
            static = Static(tool_name)
            list_item = ListItem(static, id=f"tool-{index}")
            list_item.data = tool_name
            items.append(list_item)
        return ListView(*items, id="tool-list", classes="panel")

    def compose(self) -> ComposeResult:
        app: "ToolManagerApp" = self.app  # type: ignore[assignment]
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
                    Static("", id="step2-error", classes="step-error"),
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
        app: "ToolManagerApp" = self.app  # type: ignore[assignment]
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
        app: "ToolManagerApp" = self.app  # type: ignore[assignment]
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
        args_value = args_field.value.strip()
        args = shlex.split(args_value) if args_value else []
        if self._args_include_output(args):
            self._set_error("Remove -o/--output flags here. Configure outputs in Step 3.")
            self.app.bell()
            return
        app.add_stage(tool_name, args)
        args_field.value = ""
        self.refresh_pipeline_view()
        self._set_error("")

    @on(Button.Pressed, "#remove-stage")
    def handle_remove_stage(self) -> None:
        app: "ToolManagerApp" = self.app  # type: ignore[assignment]
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
        self._set_error("")

    @on(Button.Pressed, "#next-step2")
    def handle_next(self) -> None:
        app: "ToolManagerApp" = self.app  # type: ignore[assignment]
        self._set_error("")
        if not app.pipeline:
            self.app.bell()
            return
        if not self._validate_pipeline_outputs(app):
            self.app.bell()
            return
        app.ensure_output_defaults()
        self.app.push_screen(StepThreeScreen())

    @on(Button.Pressed, "#back-step2")
    def handle_back(self) -> None:
        self.app.pop_screen()

    def _set_error(self, message: str) -> None:
        error_label = self.query_one("#step2-error", Static)
        error_label.update(message)

    def _validate_pipeline_outputs(self, app: "ToolManagerApp") -> bool:
        for stage in app.pipeline:
            if self._args_include_output(stage.args):
                self._set_error(
                    f"Stage '{stage.name}' cannot include -o/--output here. Configure outputs in Step 3."
                )
                return False
        self._set_error("")
        return True

    @staticmethod
    def _args_include_output(args: list[str]) -> bool:
        for arg in args:
            normalized = arg.strip()
            normalized_lower = normalized.lower()
            if normalized_lower in ("-o", "--output"):
                return True
            if normalized_lower.startswith("--output=") or normalized_lower.startswith("-o="):
                return True
        return False
