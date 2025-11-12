from __future__ import annotations

from textual.widgets import ListItem, Static


class StepListItem(ListItem):
    """Reusable list item with label access for files/output lists."""

    def __init__(self, label: str) -> None:
        self.label_widget = Static(label, expand=True)
        super().__init__(self.label_widget)
