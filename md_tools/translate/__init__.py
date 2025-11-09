from __future__ import annotations

from .text import TranslationError, translate_text, register_parser as register_text_parser
from .translate_md import (
    register_parser as register_markdown_parser,
    translate_markdown_async,
)

__all__ = [
    "TranslationError",
    "translate_text",
    "register_text_parser",
    "register_markdown_parser",
    "translate_markdown_async",
]


