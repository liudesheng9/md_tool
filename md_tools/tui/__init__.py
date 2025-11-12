from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable, Sequence

from .types import TUIResult


def launch_tui(
    root: Path,
    initial_tokens: Sequence[str],
    parser_factory: Callable[[], "argparse.ArgumentParser"] | None = None,
) -> TUIResult | None:
    try:
        from .app import MdToolTUI
    except ImportError as exc:  # pragma: no cover - textual missing
        raise RuntimeError(
            "The Textual dependency is required for the md-tool TUI. "
            "Install with `pip install textual`."
        ) from exc

    app = MdToolTUI(root, initial_tokens, parser_factory=parser_factory)
    try:
        return app.run()
    except KeyboardInterrupt:
        return None


__all__ = ["launch_tui", "TUIResult"]
