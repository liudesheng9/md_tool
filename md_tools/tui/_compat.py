from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import Static

try:  # Textual 0.60+ provides TextLog
    from textual.widgets import TextLog as _TextLog  # type: ignore
except ImportError:  # pragma: no cover - compatibility shim
    class TextLog(VerticalScroll):
        """Minimal shim that mimics TextLog.write for older Textual releases."""

        def __init__(self, *_, id: str | None = None, classes: str | None = None, **__) -> None:
            super().__init__(id=id, classes=classes)

        def write(self, line: str) -> None:
            if not line:
                line = ""
            self.mount(Static(line, classes="log-line"))

        def clear(self) -> None:
            for child in list(self.children):
                child.remove()
else:  # pragma: no cover - direct re-export
    class TextLog(_TextLog):
        pass

try:
    from textual.widgets import Rule as _Rule  # type: ignore
except ImportError:  # pragma: no cover - compatibility shim
    class Rule(Static):
        """Fallback horizontal rule."""

        def __init__(self, *, classes: str | None = None) -> None:
            super().__init__("─" * 40, classes=classes)
else:  # pragma: no cover - direct re-export
    class Rule(_Rule):
        pass

__all__ = ["TextLog", "Rule"]
