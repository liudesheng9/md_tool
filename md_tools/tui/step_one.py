from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, ListItem, ListView, Static

from .step_two import StepTwoScreen

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .app import ToolManagerApp


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
        app: "ToolManagerApp" = self.app  # type: ignore[assignment]
        self.temp_selected = set(app.selected_files)
        self.refresh_file_list()

    def _label_for_path(self, path: Path) -> str:
        app: "ToolManagerApp" = self.app  # type: ignore[assignment]
        marker = "[x]" if path in self.temp_selected else "[ ]"
        relative = path.relative_to(app.root) if path.is_relative_to(app.root) else path
        return f"{marker} {relative}"

    def refresh_file_list(self) -> None:
        app: "ToolManagerApp" = self.app  # type: ignore[assignment]
        list_view = self.query_one("#file-list", ListView)
        for child in list(list_view.children):
            child.remove()
        for path in app.available_files:
            label = Static(self._label_for_path(path), markup=False)
            item = ListItem(label)
            item.data = str(path)
            list_view.append(item)

    @on(Button.Pressed, "#next-step1")
    def handle_next(self) -> None:
        app: "ToolManagerApp" = self.app  # type: ignore[assignment]
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
        self._update_item_marker(event.item, path)

    def _update_item_marker(self, item: ListItem, path: Path) -> None:
        try:
            label = item.query_one(Static)
        except Exception:  # pragma: no cover - Textual internals
            return
        label.update(self._label_for_path(path))
