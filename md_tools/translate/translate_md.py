from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
import time
import threading
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Dict, Any
import json

from ..pipeline.core import PipelineOutputSpec
from ..tools.base import MDTool
from ..tools import register_tool
from ..utils import detect_newline, normalise_paragraph_newlines
from .cancellation import TranslationCancelToken, TranslationCancelled
from .text import TranslationError, translate_text


class TranslateMarkdownTool(MDTool):
    name = "translate-md"
    help_text = "Translate a Markdown file paragraph by paragraph using Google Translate."

    def __init__(self) -> None:
        self._cancel_lock = threading.Lock()
        self._active_cancel_token: Optional[TranslationCancelToken] = None

    def configure_parser(self, parser) -> None:
        parser.add_argument(
            "input",
            type=Path,
            nargs="?",
            help="Path to the input Markdown file. Optional in pipeline mode when upstream data is provided.",
        )
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
        parser.add_argument(
            "--delay-min",
            type=float,
            default=0,
            help="Minimum delay in seconds after each translation request (default: 1.0).",
        )
        parser.add_argument(
            "--delay-max",
            type=float,
            default=0.1,
            help="Maximum delay in seconds after each translation request (default: 1.5).",
        )
        parser.add_argument(
            "--bulk-delay-every",
            type=int,
            default=10,
            help="After this many requests, add an extra randomized delay (0 disables bulk delays).",
        )
        parser.add_argument(
            "--bulk-delay-min",
            type=float,
            default=0.5,
            help="Minimum bulk delay in seconds when bulk delays are enabled (default: 2.0).",
        )
        parser.add_argument(
            "--bulk-delay-max",
            type=float,
            default=5.0,
            help="Maximum bulk delay in seconds when bulk delays are enabled (default: 4.0).",
        )
        parser.add_argument(
            "--retry-count",
            type=int,
            default=5,
            help="Number of times to retry a failed translation request (default: 3).",
        )
        parser.add_argument(
            "--retry-delay-min",
            type=float,
            default=2.0,
            help="Minimum delay in seconds before retrying a failed request (default: 2.0).",
        )
        parser.add_argument(
            "--retry-delay-max",
            type=float,
            default=5.0,
            help="Maximum delay in seconds before retrying a failed request (default: 5.0).",
        )
        parser.add_argument(
            "--debug-output",
            type=Path,
            help="Optional path to write paragraph detection metadata as JSON.",
        )

    def run(self, args) -> int:
        if args.input is None:
            sys.stderr.write("Input file is required when not running in pipeline mode.\n")
            return 1

        if not args.input.is_file():
            sys.stderr.write(f"Input file not found: {args.input}\n")
            return 1

        text = args.input.read_text(encoding="utf-8")

        try:
            result, debug_records = self.translate_document(text, args, enable_progress=True)
        except KeyboardInterrupt:
            self.cancel_active_translation()
            raise
        except (ValueError, TranslationError) as exc:
            sys.stderr.write(f"{exc}\n")
            return 1
        except Exception as exc:
            sys.stderr.write(f"Translation failed: {exc}\n")
            return 1

        if args.debug_output:
            try:
                self.write_debug_output(
                    args.debug_output,
                    source=str(args.input),
                    target=str(args.output) if args.output else None,
                    records=debug_records,
                )
            except OSError as exc:
                sys.stderr.write(f"Failed to write debug output: {exc}\n")

        if args.output:
            args.output.write_text(result, encoding="utf-8")
            print(f"Wrote translated Markdown to {args.output}")
        else:
            print(result, end="")

        return 0

    def run_pipeline(self, args, artifact):
        from ..pipeline.translate_md import run_stage  # noqa: WPS433

        return run_stage(self, args, artifact)

    def pipeline_caps(self) -> MDTool.PipelineCaps:
        # One input document; one output document (debug is a side artifact)
        return MDTool.PipelineCaps(
            allow_stage_input=False,
            input_mode="single",
            output_mode="single",
        )

    def pipeline_output_spec(self) -> PipelineOutputSpec | None:
        return _TranslateMarkdownOutputSpec()

    def cancel_active_translation(self) -> None:
        with self._cancel_lock:
            token = self._active_cancel_token
        if token is not None:
            token.cancel()

    def _set_active_token(self, token: TranslationCancelToken) -> None:
        with self._cancel_lock:
            self._active_cancel_token = token

    def _clear_active_token(self, token: TranslationCancelToken) -> None:
        with self._cancel_lock:
            if self._active_cancel_token is token:
                self._active_cancel_token = None

    def translate_document(self, text: str, args, *, enable_progress: bool):
        cancel_token = TranslationCancelToken()
        self._set_active_token(cancel_token)
        try:
            return translate_markdown_document(
                text=text,
                source_language=args.source,
                target_language=args.target,
                timeout=args.timeout,
                workers=args.workers,
                delay_min=args.delay_min,
                delay_max=args.delay_max,
                bulk_delay_every=args.bulk_delay_every,
                bulk_delay_min=args.bulk_delay_min,
                bulk_delay_max=args.bulk_delay_max,
                retry_count=args.retry_count,
                retry_delay_min=args.retry_delay_min,
                retry_delay_max=args.retry_delay_max,
                enable_progress=enable_progress,
                cancel_token=cancel_token,
            )
        except TranslationCancelled as exc:
            cancel_token.cancel()
            raise KeyboardInterrupt from exc
        except KeyboardInterrupt:
            cancel_token.cancel()
            raise
        finally:
            cancel_token.cancel()
            self._clear_active_token(cancel_token)

    def write_debug_output(self, path: Path, *, source: Optional[str], target: Optional[str], records: List[Dict[str, Any]]) -> None:
        _write_debug_output(path, source, target, records)


tool = TranslateMarkdownTool()
register_tool(tool, category="transform")


def register_parser(subparsers) -> None:
    tool.register(subparsers)


class _TranslateMarkdownOutputSpec(PipelineOutputSpec):
    def resolve(self, args) -> tuple[Path, ...]:
        outputs: list[Path] = []
        output = getattr(args, "output", None)
        if output:
            outputs.append(output)
        debug_output = getattr(args, "debug_output", None)
        if debug_output:
            outputs.append(debug_output)
        return tuple(outputs)


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


def _is_table_line(stripped: str) -> bool:
    if not stripped:
        return False
    if stripped.startswith("|"):
        return True
    if stripped.startswith("+-") or stripped.startswith("|-"):
        return True
    return all(char in "|:+-=_ " for char in stripped) and "|" in stripped


def _is_image_line(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("![") and ("](" in stripped or "] [" in stripped)


def _is_reference_definition(stripped: str) -> bool:
    if not stripped.startswith("["):
        return False
    closing = stripped.find("]:")
    return closing != -1


def _is_html_block_start(stripped: str) -> bool:
    if not stripped.startswith("<") or not stripped.endswith(">"):
        return False
    if stripped.startswith("</"):
        return False
    return True


def _is_html_block_end(stripped: str) -> bool:
    if stripped.startswith("</") and stripped.endswith(">"):
        return True
    if stripped.endswith("/>"):
        return True
    if stripped.startswith("<!") and stripped.endswith("-->"):
        return True
    return False


def _count_equation_delimiters(stripped: str) -> int:
    return stripped.count("$$")


def _is_equation_single_line(stripped: str) -> bool:
    if "$$" not in stripped:
        return False
    if stripped == "$$":
        return False
    count = _count_equation_delimiters(stripped)
    return count >= 2 and stripped.startswith("$$") and stripped.endswith("$$")


def _collect_paragraphs(text: str, newline: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    lines = text.split(newline)
    paragraphs: List[str] = []
    metadata: List[Dict[str, Any]] = []
    buffer: List[str] = []
    state: Optional[str] = None
    state_start: Optional[int] = None
    equation_parity = 0
    i = 0

    def add_paragraph(kind: str, content_lines: List[str], start_idx: int, end_idx: int) -> None:
        paragraphs.append(newline.join(content_lines))
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
            equation_parity = (equation_parity + _count_equation_delimiters(stripped)) % 2
            if equation_parity == 0:
                add_paragraph("equation", buffer, state_start if state_start is not None else i - len(buffer) + 1, i)
                buffer = []
                state = None
                state_start = None
            i += 1
            continue

        if state == "html":
            buffer.append(line)
            if _is_html_block_end(stripped):
                add_paragraph("html", buffer, state_start if state_start is not None else i - len(buffer) + 1, i)
                buffer = []
                state = None
                state_start = None
            i += 1
            continue

        if state == "table":
            if _is_table_line(stripped):
                buffer.append(line)
                i += 1
                continue
            add_paragraph("table", buffer, state_start if state_start is not None else i - len(buffer), i - 1)
            buffer = []
            state = None
            state_start = None
            continue

        if state == "image":
            if _is_reference_definition(stripped):
                buffer.append(line)
                i += 1
                continue
            add_paragraph("image_block", buffer, state_start if state_start is not None else i - len(buffer), i - 1)
            buffer = []
            state = None
            state_start = None
            continue

        if not stripped:
            add_paragraph("blank", [line], i, i)
            i += 1
            continue

        if _is_image_line(line):
            buffer = [line]
            state = "image"
            state_start = i
            i += 1
            continue

        delimiter_count = _count_equation_delimiters(stripped)
        if delimiter_count:
            if _is_equation_single_line(stripped):
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

        if _is_html_block_start(stripped):
            if "</" in stripped and stripped.count("<") == stripped.count("</") + 1:
                add_paragraph("html_single", [line], i, i)
            elif "</" in stripped and stripped.count("</") >= 1 and stripped.count("<") > 1:
                add_paragraph("html_single", [line], i, i)
            else:
                buffer = [line]
                state = "html"
                state_start = i
                if _is_html_block_end(stripped):
                    add_paragraph("html_single", buffer, state_start, i)
                    buffer = []
                    state = None
                    state_start = None
            i += 1
            continue

        if _is_table_line(stripped):
            buffer = [line]
            state = "table"
            state_start = i
            i += 1
            continue

        if _is_reference_definition(stripped):
            add_paragraph("reference", [line], i, i)
            i += 1
            continue

        add_paragraph("text", [line], i, i)
        i += 1

    if state and buffer:
        add_paragraph(state, buffer, state_start if state_start is not None else len(lines) - len(buffer), len(lines) - 1)

    return paragraphs, metadata


class RequestDelayer:
    def __init__(
        self,
        min_delay: float,
        max_delay: float,
        bulk_every: int = 0,
        bulk_min_delay: float = 0.0,
        bulk_max_delay: float = 0.0,
        cancel_token: Optional[TranslationCancelToken] = None,
    ) -> None:
        if min_delay < 0 or max_delay < 0:
            raise ValueError("Delay values must be non-negative.")
        if max_delay < min_delay:
            raise ValueError("Maximum delay must be greater than or equal to minimum delay.")
        if bulk_every < 0:
            raise ValueError("Bulk delay frequency must be zero or positive.")
        if bulk_min_delay < 0 or bulk_max_delay < 0:
            raise ValueError("Bulk delay values must be non-negative.")
        if bulk_max_delay < bulk_min_delay:
            raise ValueError("Bulk maximum delay must be greater than or equal to minimum delay.")

        self._min_delay = min_delay
        self._max_delay = max_delay
        self._bulk_every = bulk_every
        self._bulk_min_delay = bulk_min_delay
        self._bulk_max_delay = bulk_max_delay
        self._lock = threading.Lock()
        self._counter = 0
        self._cancel_token = cancel_token

    def _sleep_random(self, min_delay: float, max_delay: float) -> None:
        if max_delay == 0 and min_delay == 0:
            return
        delay = random.uniform(min_delay, max_delay)
        if delay > 0:
            if self._cancel_token:
                self._cancel_token.wait(delay)
                self._cancel_token.raise_if_cancelled()
            else:
                time.sleep(delay)

    def pause(self) -> None:
        with self._lock:
            self._counter += 1
            request_count = self._counter

        self._sleep_random(self._min_delay, self._max_delay)

        if self._bulk_every and request_count % self._bulk_every == 0:
            self._sleep_random(self._bulk_min_delay, self._bulk_max_delay)


class StructureDetector:
    def __init__(self) -> None:
        self._equation_open = False
        self._html_open = False
        self._in_table = False

    def should_translate(self, line: str) -> bool:
        stripped = line.strip()

        if self._equation_open:
            if _count_equation_delimiters(stripped) % 2 == 1:
                self._equation_open = False
            return False

        if self._html_open:
            if _is_html_block_end(stripped):
                self._html_open = False
            return False

        if self._in_table:
            if _is_table_line(stripped):
                return False
            self._in_table = False

        if not stripped:
            return True

        delimiter_count = _count_equation_delimiters(stripped)
        if delimiter_count:
            if _is_equation_single_line(stripped):
                return False
            if delimiter_count % 2 == 1:
                self._equation_open = True
            return False

        if _is_html_block_start(stripped):
            if not _is_html_block_end(stripped):
                self._html_open = True
            return False

        if _is_table_line(stripped):
            self._in_table = True
            return False

        if _is_image_line(line):
            return False

        if _is_reference_definition(stripped):
            return False

        return True


def _segment_paragraph(paragraph: str) -> List[Tuple[List[str], bool]]:
    lines = paragraph.splitlines()
    if not lines:
        return [([], True)]

    detector = StructureDetector()
    segments: List[Tuple[List[str], bool]] = []
    current_lines: List[str] = []
    current_translate = True

    for line in lines:
        should_translate = detector.should_translate(line)

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


def _sleep_between_retries(
    min_delay: float,
    max_delay: float,
    cancel_token: Optional[TranslationCancelToken] = None,
) -> None:
    if min_delay <= 0 and max_delay <= 0:
        return
    lower = max(0.0, min_delay)
    upper = max(lower, max_delay)
    delay = random.uniform(lower, upper) if upper > lower else upper
    if delay > 0:
        if cancel_token:
            cancel_token.wait(delay)
            cancel_token.raise_if_cancelled()
        else:
            time.sleep(delay)


def _translate_with_retry(
    text: str,
    *,
    source_language: str,
    target_language: str,
    timeout: float,
    max_retries: int,
    retry_delay_min: float,
    retry_delay_max: float,
    cancel_token: Optional[TranslationCancelToken] = None,
) -> str:
    attempts = max(0, max_retries) + 1
    for attempt_index in range(attempts):
        if cancel_token:
            cancel_token.raise_if_cancelled()
        try:
            return translate_text(
                text=text,
                target_language=target_language,
                source_language=source_language,
                timeout=timeout,
            )
        except TranslationError as exc:
            if attempt_index == attempts - 1:
                raise
            retry_number = attempt_index + 1
            total_retries = max(1, max_retries)
            sys.stderr.write(
                f"\n[translate-md] Translation failed ({exc}); retry {retry_number}/{total_retries} after backoff.\n"
            )
            sys.stderr.flush()
            _sleep_between_retries(retry_delay_min, retry_delay_max, cancel_token)


def _translate_paragraph(
    paragraph: str,
    source_language: str,
    target_language: str,
    timeout: float,
    delayer: RequestDelayer,
    max_retries: int,
    retry_delay_min: float,
    retry_delay_max: float,
    cancel_token: Optional[TranslationCancelToken] = None,
) -> str:
    token = cancel_token or TranslationCancelToken()
    token.raise_if_cancelled()
    segments = _segment_paragraph(paragraph)

    output_lines: List[str] = []
    translated_any = False
    for lines, should_translate in segments:
        token.raise_if_cancelled()
        if should_translate:
            block = "\n".join(lines)
            normalised = _normalise_paragraph(block)
            if normalised.strip():
                translated = _translate_with_retry(
                    normalised,
                    source_language=source_language,
                    target_language=target_language,
                    timeout=timeout,
                    max_retries=max_retries,
                    retry_delay_min=retry_delay_min,
                    retry_delay_max=retry_delay_max,
                    cancel_token=token,
                )
                translated_lines = translated.splitlines()
                if translated_lines:
                    output_lines.extend(translated_lines)
                elif translated:
                    output_lines.append(translated)
                translated_any = translated_any or bool(translated.strip())
                delayer.pause()
                token.raise_if_cancelled()
        else:
            output_lines.extend(lines)

    if not translated_any:
        return ""

    return "\n".join(output_lines)


def translate_markdown_async(
    paragraphs: List[str],
    source_language: str,
    target_language: str,
    timeout: float,
    max_workers: int = 5,
    progress_callback: Optional[Callable[[int], None]] = None,
    delayer: Optional[RequestDelayer] = None,
    max_retries: int = 0,
    retry_delay_min: float = 0.0,
    retry_delay_max: float = 0.0,
    cancel_token: Optional[TranslationCancelToken] = None,
) -> List[str]:
    if max_workers < 1:
        raise ValueError("Worker count must be at least 1.")

    token = cancel_token or TranslationCancelToken()
    total = len(paragraphs)
    translated: List[Optional[str]] = [None] * total
    active_delayer = delayer or RequestDelayer(0.0, 0.0, cancel_token=token)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _translate_paragraph,
                paragraph,
                source_language,
                target_language,
                timeout,
                active_delayer,
                max_retries,
                retry_delay_min,
                retry_delay_max,
                token,
            ): index
            for index, paragraph in enumerate(paragraphs)
        }

        completed = 0
        try:
            for future in as_completed(futures):
                if token.is_cancelled():
                    raise TranslationCancelled()
                index = futures[future]
                translation = future.result()
                translated[index] = translation
                completed += 1
                if progress_callback:
                    progress_callback(completed)
        except TranslationCancelled:
            for pending in futures:
                pending.cancel()
            raise
        except Exception:
            for pending in futures:
                pending.cancel()
            raise

    return [text if text is not None else "" for text in translated]


def _build_debug_records(
    paragraphs: List[str],
    paragraph_metadata: List[Dict[str, Any]],
    translations: List[str],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    debug_records: List[Dict[str, Any]] = []
    bilingual_paragraphs: List[str] = []

    for index, (original, translation) in enumerate(zip(paragraphs, translations)):
        original_block = _normalise_paragraph(original)
        translated_clean = translation.strip()

        if index < len(paragraph_metadata):
            record = dict(paragraph_metadata[index])
        else:
            record = {
                "type": "unknown",
                "lines": [original],
                "line_start": index,
                "line_end": index,
            }

        record.update(
            {
                "index": index,
                "original": original,
                "translation": translation,
                "translated": bool(translated_clean),
            }
        )
        debug_records.append(record)

        if translated_clean:
            bilingual_block = f"{original_block}\n\n{translation}"
        else:
            bilingual_block = original_block
        bilingual_paragraphs.append(bilingual_block)

    return debug_records, bilingual_paragraphs


def _write_debug_output(path: Path, source: Optional[str], target: Optional[str], records: List[Dict[str, Any]]) -> None:
    payload = {
        "source": source,
        "target": target,
        "paragraphs": records,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def translate_markdown_document(
    text: str,
    *,
    source_language: str,
    target_language: str,
    timeout: float,
    workers: int,
    delay_min: float,
    delay_max: float,
    bulk_delay_every: int,
    bulk_delay_min: float,
    bulk_delay_max: float,
    retry_count: int,
    retry_delay_min: float,
    retry_delay_max: float,
    enable_progress: bool = True,
    cancel_token: Optional[TranslationCancelToken] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    cancel = cancel_token or TranslationCancelToken()

    newline = detect_newline(text)
    paragraphs, paragraph_metadata = _collect_paragraphs(text, newline)

    if not any(paragraph.strip() for paragraph in paragraphs):
        raise ValueError("The document does not contain any content.")

    if retry_count < 0:
        raise ValueError("Retry count must be zero or greater.")
    retry_delay_min = max(0.0, retry_delay_min)
    retry_delay_max = max(retry_delay_min, retry_delay_max)

    cancel.raise_if_cancelled()

    progress = ProgressPrinter(len(paragraphs)) if enable_progress else None
    try:
        delayer = RequestDelayer(
            delay_min,
            delay_max,
            bulk_every=bulk_delay_every,
            bulk_min_delay=bulk_delay_min,
            bulk_max_delay=bulk_delay_max,
            cancel_token=cancel,
        )
    except ValueError:
        if progress:
            progress.finish()
        raise

    try:
        translated = translate_markdown_async(
            paragraphs=paragraphs,
            source_language=source_language,
            target_language=target_language,
            timeout=timeout,
            max_workers=workers,
            progress_callback=progress.update if progress else None,
            delayer=delayer,
            max_retries=retry_count,
            retry_delay_min=retry_delay_min,
            retry_delay_max=retry_delay_max,
            cancel_token=cancel,
        )
    except KeyboardInterrupt:
        cancel.cancel()
        raise
    finally:
        if progress:
            progress.finish()

    debug_records, bilingual_paragraphs = _build_debug_records(
        paragraphs,
        paragraph_metadata,
        translated,
    )

    normalised = normalise_paragraph_newlines(bilingual_paragraphs, newline)
    result = newline.join(normalised)
    if text.endswith(newline):
        result += newline

    return result, debug_records
