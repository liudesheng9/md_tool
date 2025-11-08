"""Compatibility wrapper for invoking md-tool via python split_markdown.py."""

from __future__ import annotations

import sys

from md_tools.cli import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


