from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, ListView, Static


def create_files_panel() -> tuple[Vertical, ListView]:
    panel = Vertical(id="step-files", classes="step-panel")
    panel.mount(Static("Step 1: Select Markdown files (Space toggles selection)."))
    file_list = ListView(id="files-list")
    panel.mount(file_list)
    panel.mount(
        Horizontal(
            Button("Cancel", id="files-cancel", variant="error"),
            Button("Next: Pipeline", id="files-next", variant="success"),
        )
    )
    return panel, file_list
