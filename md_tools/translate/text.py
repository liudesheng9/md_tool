from __future__ import annotations

import json
import sys
from dataclasses import dataclass
import os
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


GOOGLE_TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
FAKE_TRANSLATE_ENV = "MD_TOOL_FAKE_TRANSLATE"


class TranslationError(Exception):
    """Raised when a translation request fails."""


@dataclass
class TranslationRequest:
    text: str
    target_language: str
    source_language: str = "auto"
    timeout: float = 10.0

    def __post_init__(self) -> None:
        self.text = self.text.strip()
        self.target_language = self.target_language.strip().lower()
        self.source_language = self.source_language.strip().lower()

        if not self.text:
            raise ValueError("Translation text must not be empty.")
        if not self.target_language:
            raise ValueError("Target language must not be empty.")
        if not self.source_language:
            raise ValueError("Source language must not be empty.")


def translate_text(
    text: str, target_language: str, source_language: str = "auto", timeout: float = 10.0
) -> str:
    """Translate text using the public Google Translate endpoint."""

    request = TranslationRequest(
        text=text, target_language=target_language, source_language=source_language, timeout=timeout
    )

    fake_mode = os.environ.get(FAKE_TRANSLATE_ENV)
    if fake_mode:
        return _simulate_translation(request, fake_mode)
    query = urlencode(
        {
            "client": "gtx",
            "sl": request.source_language,
            "tl": request.target_language,
            "dt": "t",
            "q": request.text,
        }
    )

    http_request = Request(
        f"{GOOGLE_TRANSLATE_URL}?{query}",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0 Safari/537.36"
            )
        },
    )

    try:
        with urlopen(http_request, timeout=request.timeout) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        raise TranslationError(f"Google Translate returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise TranslationError(f"Could not reach Google Translate: {exc.reason}") from exc

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise TranslationError("Failed to decode translation response.") from exc

    try:
        translated_segments: Iterable[str] = (
            segment[0] for segment in data[0] if segment and segment[0]
        )
    except (TypeError, IndexError) as exc:
        raise TranslationError("Unexpected response format from Google Translate.") from exc

    translation = "".join(translated_segments)
    if not translation:
        raise TranslationError("Translation response did not contain any text.")
    return translation


def _simulate_translation(request: TranslationRequest, mode: str) -> str:
    label = (mode or "stub").strip() or "stub"
    normalized = label.lower()
    if normalized == "reverse":
        payload = request.text[::-1]
    elif normalized == "identity":
        payload = request.text
    else:
        payload = request.text.upper()
    return f"[{request.source_language}->{request.target_language}|{label}] {payload}"


def register_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "translate",
        help="Translate text to a target language using Google Translate.",
    )
    parser.add_argument(
        "text",
        nargs="*",
        help="Text to translate. Leave empty to enter the text interactively.",
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
        help="Timeout for the translation request in seconds (default: 10).",
    )
    parser.set_defaults(func=run)


def run(args) -> int:
    text = " ".join(args.text).strip()
    if not text:
        try:
            text = input("Enter text to translate: ").strip()
        except EOFError:
            text = ""

    if not text:
        sys.stderr.write("No text provided for translation.\n")
        return 1

    try:
        translated = translate_text(
            text=text,
            target_language=args.target,
            source_language=args.source,
            timeout=args.timeout,
        )
    except (ValueError, TranslationError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    print(translated)
    return 0

