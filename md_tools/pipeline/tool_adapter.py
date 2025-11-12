from __future__ import annotations

import argparse
import sys
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Protocol, Sequence

from .output_utils import default_output_name, resolve_document_label
from .types import MarkdownArtifact, MarkdownDocument, PipelineStageError
from ..tui import launch_tui
from ..tui.types import TUIResult

PrintFunc = Callable[[str], None]


@dataclass(frozen=True)
class OutputAssignment:
    label: str
    document: MarkdownDocument
    destination: Path


class PipelineExecutor(Protocol):
    def __call__(
        self,
        raw_tokens: Sequence[str],
        parser_factory: Callable[[], argparse.ArgumentParser],
        *,
        input_path: Path,
    ) -> MarkdownArtifact:
        ...


class SelectionCancelled(RuntimeError):
    """Raised when the user cancels selection from the TUI."""


class ToolAdapterCommand:
    """CLI helper that wires directory-based Markdown selection into pipelines."""

    def __init__(
        self,
        *,
        parser_factory: Callable[[], argparse.ArgumentParser],
        executor: PipelineExecutor,
        output_func: PrintFunc = print,
        enable_tui: bool = True,
        tui_launcher: Callable[
            [Path, Sequence[str], Callable[[], argparse.ArgumentParser]],
            Optional[TUIResult],
        ] = launch_tui,
    ) -> None:
        self._parser_factory = parser_factory
        self._executor = executor
        self._output = output_func
        self._enable_tui = enable_tui
        self._tui_launcher = tui_launcher

    def register(self, subparsers) -> None:
        parser = subparsers.add_parser(
            "tui",
            help="Launch a TUI to select Markdown files and build pipelines.",
        )
        self._configure_parser(parser)
        parser.set_defaults(func=self.execute)

    def _configure_parser(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "root",
            type=Path,
            help="Directory to scan for Markdown files (searches recursively).",
        )
        parser.add_argument(
            "--output-dir",
            type=Path,
            help="Optional directory for writing pipeline results (defaults to the selected file's directory).",
        )

    def execute(self, args) -> int:
        root = Path(args.root).expanduser().resolve()
        if not root.exists():
            sys.stderr.write(f"Directory not found: {root}\n")
            return 1
        if not root.is_dir():
            sys.stderr.write(f"Path is not a directory: {root}\n")
            return 1

        try:
            config = self._launch_tui(root)
        except SelectionCancelled:
            sys.stderr.write("Selection cancelled.\n")
            return 1
        except RuntimeError as exc:
            sys.stderr.write(f"{exc}\n")
            return 1

        if not config.selections:
            sys.stderr.write("No files were selected.\n")
            return 1
        if not config.pipeline_tokens:
            sys.stderr.write("No pipeline stages were configured.\n")
            return 1

        stages = config.pipeline_tokens
        single_overrides = config.single_outputs
        multi_overrides = config.multi_bases

        for selection in config.selections:
            try:
                relative_selection = selection.relative_to(root)
            except ValueError:
                relative_selection = selection
            self._output("")
            self._output(f"Selected Markdown file: {relative_selection}")
            self._render_output_preview(
                selection,
                single_overrides=single_overrides,
                multi_overrides=multi_overrides,
            )

            try:
                artifact = self._executor(stages, self._parser_factory, input_path=selection)
            except PipelineStageError as exc:
                prefix = f"[{exc.stage}] " if exc.stage else ""
                sys.stderr.write(f"{prefix}{exc}\n")
                return 1

            manifest = self._write_outputs(
                selection,
                artifact,
                output_dir=args.output_dir,
                single_overrides=single_overrides,
                multi_overrides=multi_overrides,
            )
            if not manifest:
                self._output("Pipeline produced no documents to write.")
                continue

            self._output("Outputs:")
            for label, destination in manifest.items():
                self._output(f"  {label} -> {destination}")

        return 0

    # ---- Input helpers -------------------------------------------------------------
    def _launch_tui(
        self,
        root: Path,
    ) -> TUIResult:
        if not self._enable_tui:
            raise RuntimeError("The TUI is disabled in this environment.")
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise RuntimeError("md-tool tui requires an interactive terminal.")
        config = self._tui_launcher(root, [], self._parser_factory)
        if config is None:
            raise SelectionCancelled("Selection cancelled.")
        return config

    def _render_output_preview(
        self,
        selection: Path,
        *,
        single_overrides: Dict[Path, str],
        multi_overrides: Dict[Path, str],
    ) -> None:
        suffix = selection.suffix or ".md"
        single_name = self._lookup_single_override(selection, single_overrides)
        multi_base = self._lookup_multi_override(selection, multi_overrides)
        self._output("Output name mapping:")
        self._output(f"  {selection.name} -> {single_name} (single document result)")
        self._output(
            f"  {selection.name} -> {multi_base}_part_<n>{suffix} "
            "(multiple document result; '_part_<n>' will be appended)."
        )

    def _lookup_single_override(self, path: Path, overrides: Dict[Path, str]) -> str:
        if not overrides:
            return self._default_single_name(path)
        for key in (path, path.resolve()):
            if key in overrides:
                return overrides[key]
        return self._default_single_name(path)

    def _lookup_multi_override(self, path: Path, overrides: Dict[Path, str]) -> str:
        if not overrides:
            return default_output_name(path, multiple_outputs=True)
        for key in (path, path.resolve()):
            if key in overrides and overrides[key]:
                return overrides[key]
        return default_output_name(path, multiple_outputs=True)

    def _default_single_name(self, path: Path) -> str:
        candidate = default_output_name(path, multiple_outputs=False)
        suffix = path.suffix or ".md"
        if candidate.endswith(suffix):
            return candidate
        return f"{candidate}{suffix}"

    # ---- Output helpers ------------------------------------------------------------
    def _write_outputs(
        self,
        input_file: Path,
        artifact: Optional[MarkdownArtifact],
        *,
        output_dir: Optional[Path],
        single_overrides: Optional[Dict[Path, str]] = None,
        multi_overrides: Optional[Dict[Path, str]] = None,
    ) -> OrderedDict[str, Path]:
        documents = artifact.documents if artifact and artifact.documents else []
        if not documents:
            return OrderedDict()

        destination_root = (
            Path(output_dir).expanduser().resolve()
            if output_dir
            else input_file.parent
        )
        destination_root.mkdir(parents=True, exist_ok=True)

        assignments = _plan_output_assignments(
            input_file,
            documents,
            destination_root,
            single_overrides=single_overrides,
            multi_overrides=multi_overrides,
        )
        manifest: OrderedDict[str, Path] = OrderedDict()
        for assignment in assignments:
            assignment.destination.parent.mkdir(parents=True, exist_ok=True)
            assignment.destination.write_text(assignment.document.text, encoding="utf-8")
            manifest[assignment.label] = assignment.destination
        return manifest


def _plan_output_assignments(
    input_file: Path,
    documents: Sequence[MarkdownDocument],
    destination_root: Path,
    *,
    single_overrides: Optional[Dict[Path, str]] = None,
    multi_overrides: Optional[Dict[Path, str]] = None,
) -> List[OutputAssignment]:
    assignments: List[OutputAssignment] = []
    multiple_outputs = len(documents) > 1
    default_single = default_output_name(input_file, multiple_outputs=False)
    default_multi = default_output_name(input_file, multiple_outputs=True)
    single_override = None
    multi_override = None
    if single_overrides:
        single_override = single_overrides.get(input_file) or single_overrides.get(input_file.resolve())
    if multi_overrides:
        multi_override = multi_overrides.get(input_file) or multi_overrides.get(input_file.resolve())
    suffix = input_file.suffix or ".md"

    if single_override:
        single_name = single_override
    else:
        single_name = default_single if default_single.endswith(suffix) else f"{default_single}{suffix}"

    if not multiple_outputs:
        target = destination_root / single_name
        assignments.append(
            OutputAssignment(
                label=target.name,
                document=documents[0],
                destination=target,
            )
        )
        return assignments

    base_name = multi_override or default_multi or input_file.stem or "output"

    for index, document in enumerate(documents, start=1):
        label = resolve_document_label(document, base_name, index, suffix)
        assignments.append(
            OutputAssignment(
                label=label,
                document=document,
                destination=destination_root / label,
            )
        )

    return assignments


__all__ = ["ToolAdapterCommand"]
