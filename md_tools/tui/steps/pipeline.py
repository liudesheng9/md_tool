from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static


def create_pipeline_panel(default_text: str) -> tuple[Vertical, Input, Static]:
    panel = Vertical(id="step-pipeline", classes="step-panel")
    panel.mount(Static("Step 2: Build the pipeline (use '=' between stages)."))
    pipeline_input = Input(
        placeholder="translate-md --target fr = format-newlines",
        value=default_text,
        id="pipeline-input",
    )
    panel.mount(pipeline_input)
    diagram = Static("No pipeline defined.", id="pipeline-diagram")
    panel.mount(diagram)
    panel.mount(
        Horizontal(
            Button("Back", id="pipeline-back"),
            Button("Next: Outputs", id="pipeline-next", variant="success"),
        )
    )
    return panel, pipeline_input, diagram
