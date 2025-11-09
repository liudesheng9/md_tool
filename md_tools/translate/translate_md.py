from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from ..utils import collect_paragraphs, detect_newline, normalise_paragraph_newlines
from .text import TranslationError, translate_text


def register_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "translate-md",
        help="Translate a Markdown file paragraph by paragraph using Google Translate.",
    )
    parser.add_argument("input", type=Path, help="Path to the input Markdown file.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional path for the translated Markdown. Defaults to printing to stdout.",
    )
    parser.add_argument(
        "-s",
        "--source",
        default="auto",
        help="Source language code (default: auto-detect).",
    )
    parser.add_argument(
        "-t",
        "--target",
        required=True,
        help="Target language code (for example, 'es' or 'fr').",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Timeout for each translation request in seconds (default: 10).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Number of concurrent translation workers (default: 5).",
    )
    parser.set_defaults(func=run)


class ProgressPrinter:
    def __init__(self, total: int) -> None:
        self.total = total

    def update(self, current: int) -> None:
        percent = int(current * 100 / self.total) if self.total else 100
        sys.stderr.write(
            f"\rTranslating paragraphs: {current}/{self.total} ({percent:3d}%)"
        )
        sys.stderr.flush()

    def finish(self) -> None:
        if self.total:
            sys.stderr.write("\n")
            sys.stderr.flush()


def _normalise_paragraph(paragraph: str) -> str:
    return paragraph.replace("\r\n", "\n").replace("\r", "\n")


def _segment_paragraph(paragraph: str) -> List[Tuple[List[str], bool]]:
    lines = paragraph.splitlines()
    if not lines:
        return [([], True)]

    segments: List[Tuple[List[str], bool]] = []
    current_lines: List[str] = []
    current_translate = True
    in_equation = False
    in_html = False

    def classification_for_line(line: str) -> bool:
        nonlocal in_equation, in_html
        stripped = line.strip()

        if in_equation:
            if stripped.endswith("$$"):
                in_equation = False
            return False

        if in_html:
            if stripped.startswith("</") and stripped.endswith(">"):
                in_html = False
            return False

        if not stripped:
            return True

        if stripped.startswith("$$"):
            if stripped == "$$" or not stripped.endswith("$$"):
                in_equation = True
            return False

        if stripped.startswith("<"):
            if not stripped.startswith("</") and not stripped.endswith("/>") and "</" not in stripped:
                in_html = True
            return False

        if stripped.startswith("|") or stripped.startswith("+-"):
            return False

        if "![" in line and "](" in line:
            return False

        return True

    for line in lines:
        should_translate = classification_for_line(line)

        if not current_lines:
            current_lines = [line]
            current_translate = should_translate
            continue

        if should_translate == current_translate:
            current_lines.append(line)
        else:
            segments.append((current_lines, current_translate))
            current_lines = [line]
            current_translate = should_translate

    if current_lines:
        segments.append((current_lines, current_translate))

    return segments


def _translate_paragraph(
    paragraph: str,
    source_language: str,
    target_language: str,
    timeout: float,
) -> str:
    segments = _segment_paragraph(paragraph)

    translated_parts: List[str] = []
    for lines, should_translate in segments:
        block = "\n".join(lines)
        if should_translate and block.strip():
            translated = translate_text(
                text=_normalise_paragraph(block),
                target_language=target_language,
                source_language=source_language,
                timeout=timeout,
            )
            translated_parts.append(translated)
        else:
            translated_parts.append(block)

    return "\n".join(translated_parts)


def translate_markdown_async(
    paragraphs: List[str],
    source_language: str,
    target_language: str,
    timeout: float,
    max_workers: int = 5,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> List[str]:
    if max_workers < 1:
        raise ValueError("Worker count must be at least 1.")

    total = len(paragraphs)
    translated: List[Optional[str]] = [None] * total

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _translate_paragraph,
                paragraph,
                source_language,
                target_language,
                timeout,
            ): index
            for index, paragraph in enumerate(paragraphs)
        }

        completed = 0
        try:
            for future in as_completed(futures):
                index = futures[future]
                translation = future.result()
                translated[index] = translation
                completed += 1
                if progress_callback:
                    progress_callback(completed)
        except Exception:
            for pending in futures:
                pending.cancel()
            raise

    return [text if text is not None else "" for text in translated]


def run(args) -> int:
    if not args.input.is_file():
        sys.stderr.write(f"Input file not found: {args.input}\n")
        return 1

    text = args.input.read_text(encoding="utf-8")
    paragraphs = collect_paragraphs(text)

    if not paragraphs:
        sys.stderr.write("The input file does not contain any paragraphs.\n")
        return 1

    newline = detect_newline(text)
    progress = ProgressPrinter(len(paragraphs))

    try:
        translated = translate_markdown_async(
            paragraphs=paragraphs,
            source_language=args.source,
            target_language=args.target,
            timeout=args.timeout,
            max_workers=args.workers,
            progress_callback=progress.update,
        )
    except (ValueError, TranslationError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    except Exception as exc:
        sys.stderr.write(f"Translation failed: {exc}\n")
        return 1
    finally:
        progress.finish()

    bilingual_paragraphs: List[str] = []
    for original, translation in zip(paragraphs, translated):
        bilingual_block = f"{_normalise_paragraph(original)}\n\n{translation}"
        bilingual_paragraphs.append(bilingual_block)

    normalised = normalise_paragraph_newlines(bilingual_paragraphs, newline)
    separator = newline * 2
    result = separator.join(normalised)
    if result and not result.endswith(newline):
        result += newline

    if args.output:
        args.output.write_text(result, encoding="utf-8")
        print(f"Wrote translated Markdown to {args.output}")
    else:
        print(result, end="")

    return 0


