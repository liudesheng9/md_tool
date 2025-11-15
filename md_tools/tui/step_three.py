from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, ListItem, ListView, Static

from ._compat import Rule
from .constants import OUTPUT_FLAG_MAP

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .app import ToolManagerApp


class OutputField(Static):
    """Widget containing a label and editable path input."""

    class Changed(Message):
        def __init__(self, sender: "OutputField", stage_index: int, path: str) -> None:
            self.stage_index = stage_index
            self.path = path
            super().__init__()

    class Toggled(Message):
        def __init__(self, sender: "OutputField", stage_index: int, enabled: bool) -> None:
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
        self._toggle_button_id = f"output-toggle-{self.stage_index}"
        self._body_id = f"output-body-{self.stage_index}"
        self._status_id = f"output-status-{self.stage_index}"

    def compose(self) -> ComposeResult:
        label = Label(f"{self.stage_index + 1}. {self.stage_name}")
        if self.allow_disable:
            yield Horizontal(
                label,
                Static("", classes="output-field-spacer"),
                Button(
                    self._toggle_label(),
                    id=self._toggle_button_id,
                    variant="primary" if not self.enabled else "default",
                ),
                classes="output-field-header",
            )
        else:
            yield Horizontal(label, classes="output-field-header")
        yield Vertical(id=self._body_id)
        yield Static("", id=self._status_id, classes="output-status")
        yield Rule()

    def on_mount(self) -> None:
        self._render_body()
        self._update_state_feedback()

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
        body.mount(Input(value=self.value, id=self._input_id))

    def _active_input(self) -> Input | None:
        if self.allow_disable and not self.enabled:
            return None
        try:
            return self.query_one(f"#{self._input_id}", Input)
        except Exception:
            return None

    def _status_text(self) -> str:
        if not self.allow_disable:
            return f"Final output path: {self.value}"
        if self.enabled:
            return f"Intermediate output enabled -> {self.value}"
        return "Intermediate output disabled."

    def _update_status(self) -> None:
        try:
            status = self.query_one(f"#{self._status_id}", Static)
        except Exception:
            return
        status.update(self._status_text())

    def _toggle_button(self) -> Button | None:
        if not self.allow_disable:
            return None
        try:
            return self.query_one(f"#{self._toggle_button_id}", Button)
        except Exception:
            return None

    def _toggle_label(self) -> str:
        return "Disable output" if self.enabled else "Emit output"

    def _update_state_feedback(self) -> None:
        self.set_class(self.allow_disable and not self.enabled, "output-field-disabled")
        self._update_status()
        button = self._toggle_button()
        if button is not None:
            button.label = self._toggle_label()
            button.variant = "default" if self.enabled else "primary"

    @on(Input.Changed)
    def handle_change(self, event: Input.Changed) -> None:
        if self.allow_disable and not self.enabled:
            return
        self.value = event.value
        self.post_message(OutputField.Changed(self, self.stage_index, event.value))
        self._update_status()

    @on(Button.Pressed)
    def handle_toggle(self, event: Button.Pressed) -> None:
        if not self.allow_disable or event.button.id != self._toggle_button_id:
            return
        self.enabled = not self.enabled
        self._render_body()
        input_widget = self._active_input()
        if input_widget is not None:
            input_widget.value = self.value
            input_widget.focus()
        self.post_message(OutputField.Toggled(self, self.stage_index, self.enabled))
        self._update_state_feedback()


class StepThreeScreen(Screen):
    """Output configuration screen."""

    def __init__(self) -> None:
        super().__init__()
        self.current_file: Path | None = None

    def compose(self) -> ComposeResult:
        app: "ToolManagerApp" = self.app  # type: ignore[assignment]
        yield Header()
        yield Vertical(
            Static("Step 3/4 - Configure output paths", classes="step-title"),
            Static(
                "Intermediate stages start disabled. Use the Emit output button to opt in; the final output is always required.",
                classes="step-help",
            ),
            Horizontal(
                Vertical(
                    Static("Inputs"),
                    self._build_output_file_list(app),
                    id="output-file-column",
                    classes="input-column",
                ),
                Vertical(
                    Static("Outputs"),
                    VerticalScroll(id="output-editor", classes="panel"),
                    id="output-path-column",
                    classes="output-column",
                ),
                classes="output-columns",
            ),
            Horizontal(
                Button("Run Pipelines", id="run-pipelines", variant="primary"),
                Button("Back", id="back-step3"),
                classes="step-actions",
            ),
            id="step-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        app: "ToolManagerApp" = self.app  # type: ignore[assignment]
        app.ensure_output_defaults()
        file_list = self.query_one("#output-file-list", ListView)
        if file_list.children:
            first = file_list.children[0]
            data = getattr(first, "data", "")
            if data:
                self.current_file = Path(str(data)).resolve()
                file_list.index = 0
                self.refresh_output_fields()

    def refresh_output_fields(self) -> None:
        if not self.current_file:
            return
        app: "ToolManagerApp" = self.app  # type: ignore[assignment]
        editor = self.query_one("#output-editor", VerticalScroll)
        for child in list(editor.children):
            child.remove()
        overrides = app.output_overrides.get(self.current_file, {})
        disabled = app.output_disabled.setdefault(self.current_file, set())
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

    def _build_output_file_list(self, app: "ToolManagerApp") -> ListView:
        items: list[ListItem] = []
        for path in app.selected_files:
            label = Static(str(path.relative_to(app.root)))
            item = ListItem(label)
            item.data = str(path)
            items.append(item)
        return ListView(*items, id="output-file-list", classes="panel")

    @on(ListView.Highlighted, "#output-file-list")
    def on_file_selected(self, event: ListView.Highlighted) -> None:
        data = event.item.data
        if data:
            self.current_file = Path(str(data)).resolve()
            self.refresh_output_fields()

    @on(OutputField.Changed)
    def on_output_changed(self, event: OutputField.Changed) -> None:
        if not self.current_file:
            return
        app: "ToolManagerApp" = self.app  # type: ignore[assignment]
        app.update_output_override(self.current_file, event.stage_index, event.path)

    @on(OutputField.Toggled)
    def on_output_toggled(self, event: OutputField.Toggled) -> None:
        if not self.current_file:
            return
        app: "ToolManagerApp" = self.app  # type: ignore[assignment]
        app.update_output_disabled(self.current_file, event.stage_index, not event.enabled)

    @on(Button.Pressed, "#run-pipelines")
    def handle_run(self) -> None:
        app: "ToolManagerApp" = self.app  # type: ignore[assignment]
        if not app.pipeline or not app.selected_files:
            self.app.bell()
            return
        app.start_pipeline_run()

    @on(Button.Pressed, "#back-step3")
    def handle_back(self) -> None:
        self.app.pop_screen()
