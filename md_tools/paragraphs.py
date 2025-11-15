from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .utils import detect_newline


def count_equation_delimiters(stripped: str) -> int:
    return stripped.count("$$")


def is_equation_single_line(stripped: str) -> bool:
    if "$$" not in stripped:
        return False
    if stripped == "$$":
        return False
    count = count_equation_delimiters(stripped)
    return count >= 2 and stripped.startswith("$$") and stripped.endswith("$$")


def is_table_line(stripped: str) -> bool:
    if not stripped:
        return False
    if stripped.startswith("|"):
        return True
    if stripped.startswith("+-") or stripped.startswith("|-"):
        return True
    return all(char in "|:+-=_ " for char in stripped) and "|" in stripped


def is_image_line(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("![") and ("](" in stripped or "] [" in stripped)


def is_reference_definition(stripped: str) -> bool:
    if not stripped.startswith("["):
        return False
    closing = stripped.find("]:")
    return closing != -1


def is_html_block_start(stripped: str) -> bool:
    if not stripped.startswith("<") or not stripped.endswith(">"):
        return False
    if stripped.startswith("</"):
        return False
    return True


def is_html_block_end(stripped: str) -> bool:
    if stripped.startswith("</") and stripped.endswith(">"):
        return True
    if stripped.endswith("/>"):
        return True
    if stripped.startswith("<!") and stripped.endswith("-->"):
        return True
    return False


class MarkdownParagraphExtractor:
    """Parse Markdown text into paragraphs with structural metadata."""

    def __init__(self, newline: str) -> None:
        self.newline = newline or "\n"

    def collect(self, text: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        lines = text.split(self.newline)
        paragraphs: List[str] = []
        metadata: List[Dict[str, Any]] = []
        buffer: List[str] = []
        state: Optional[str] = None
        state_start: Optional[int] = None
        equation_parity = 0
        fence_marker: Optional[str] = None
        i = 0

        def add_paragraph(kind: str, content_lines: List[str], start_idx: int, end_idx: int) -> None:
            paragraphs.append(self.newline.join(content_lines))
            metadata.append(
                {
                    "type": kind,
                    "lines": content_lines[:],
                    "line_start": start_idx,
                    "line_end": end_idx,
                }
            )

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if state == "equation":
                buffer.append(line)
                equation_parity = (equation_parity + count_equation_delimiters(stripped)) % 2
                if equation_parity == 0:
                    add_paragraph(
                        "equation",
                        buffer,
                        state_start if state_start is not None else i - len(buffer) + 1,
                        i,
                    )
                    buffer = []
                    state = None
                    state_start = None
                i += 1
                continue

            if state == "html":
                buffer.append(line)
                if is_html_block_end(stripped):
                    add_paragraph(
                        "html",
                        buffer,
                        state_start if state_start is not None else i - len(buffer) + 1,
                        i,
                    )
                    buffer = []
                    state = None
                    state_start = None
                i += 1
                continue

            if state == "table":
                if is_table_line(stripped):
                    buffer.append(line)
                    i += 1
                    continue
                add_paragraph(
                    "table",
                    buffer,
                    state_start if state_start is not None else i - len(buffer),
                    i - 1,
                )
                buffer = []
                state = None
                state_start = None
                continue

            if state == "image":
                if is_reference_definition(stripped):
                    buffer.append(line)
                    i += 1
                    continue
                add_paragraph(
                    "image_block",
                    buffer,
                    state_start if state_start is not None else i - len(buffer),
                    i - 1,
                )
                buffer = []
                state = None
                state_start = None
                continue

            if state == "fence":
                buffer.append(line)
                if fence_marker and stripped.startswith(fence_marker):
                    add_paragraph(
                        "code_fence",
                        buffer,
                        state_start if state_start is not None else i - len(buffer) + 1,
                        i,
                    )
                    buffer = []
                    state = None
                    state_start = None
                    fence_marker = None
                i += 1
                continue

            if not stripped:
                add_paragraph("blank", [line], i, i)
                i += 1
                continue

            if is_image_line(line):
                buffer = [line]
                state = "image"
                state_start = i
                i += 1
                continue

            if stripped.startswith("```") or stripped.startswith("~~~"):
                buffer = [line]
                state = "fence"
                state_start = i
                fence_marker = stripped[:3]
                i += 1
                continue

            delimiter_count = count_equation_delimiters(stripped)
            if delimiter_count:
                if is_equation_single_line(stripped):
                    add_paragraph("equation_single", [line], i, i)
                    i += 1
                    continue

                buffer = [line]
                state = "equation"
                state_start = i
                equation_parity = delimiter_count % 2
                if equation_parity == 0:
                    add_paragraph("equation_single", buffer, state_start, i)
                    buffer = []
                    state = None
                    state_start = None
                i += 1
                continue

            if is_html_block_start(stripped):
                if "</" in stripped and stripped.count("<") == stripped.count("</") + 1:
                    add_paragraph("html_single", [line], i, i)
                elif "</" in stripped and stripped.count("</") >= 1 and stripped.count("<") > 1:
                    add_paragraph("html_single", [line], i, i)
                else:
                    buffer = [line]
                    state = "html"
                    state_start = i
                    if is_html_block_end(stripped):
                        add_paragraph("html_single", buffer, state_start, i)
                        buffer = []
                        state = None
                        state_start = None
                i += 1
                continue

            if is_table_line(stripped):
                buffer = [line]
                state = "table"
                state_start = i
                i += 1
                continue

            if is_reference_definition(stripped):
                add_paragraph("reference", [line], i, i)
                i += 1
                continue

            add_paragraph("text", [line], i, i)
            i += 1

        if state and buffer:
            add_paragraph(
                state,
                buffer,
                state_start if state_start is not None else len(lines) - len(buffer),
                len(lines) - 1,
            )

        return paragraphs, metadata


def collect_paragraphs_with_metadata(
    text: str,
    *,
    newline: Optional[str] = None,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    newline_value = newline or detect_newline(text)
    extractor = MarkdownParagraphExtractor(newline_value)
    return extractor.collect(text)


def collect_paragraphs(text: str, *, newline: Optional[str] = None) -> List[str]:
    paragraphs, _ = collect_paragraphs_with_metadata(text, newline=newline)
    return paragraphs
