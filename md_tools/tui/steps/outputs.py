from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, ListView, Static


def create_outputs_panel() -> tuple[Vertical, ListView, Input, Input, Static]:
    panel = Vertical(id="step-outputs", classes="step-panel")
    panel.mount(Static("Step 3: Choose a file, then edit its single/multi output names."))

    columns = Horizontal(id="outputs-columns")

    list_container = Vertical(id="outputs-list-pane")
    list_container.mount(Static("Selected files"))
    output_file_list = ListView(id="output-files")
    list_container.mount(output_file_list)
    columns.mount(list_container)

    editor = Vertical(id="outputs-editor")
    editor.mount(Static("Output names"))
    single_input = Input(
        placeholder="Single output filename (e.g. chapter_out.md)",
        id="single-output-input",
    )
    multi_input = Input(
        placeholder="Multi-output base (e.g. chapter_out)",
        id="multi-output-input",
    )
    editor.mount(single_input)
    editor.mount(multi_input)
    preview = Static("Select a file to preview names.", id="output-preview")
    editor.mount(preview)
    columns.mount(editor)

    panel.mount(columns)
    panel.mount(
        Horizontal(
            Button("Back", id="outputs-back"),
            Button("Run pipeline", id="outputs-run", variant="success"),
        )
    )
    return panel, output_file_list, single_input, multi_input, preview
