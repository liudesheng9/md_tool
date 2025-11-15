from __future__ import annotations

import asyncio
import io
from contextlib import redirect_stderr, redirect_stdout
from typing import TYPE_CHECKING, Callable

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from ._compat import TextLog

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .app import ToolManagerApp


class StepFourScreen(Screen):
    """Final page that surfaces pipeline execution results."""

    RUNNING_STATUS = "The selected pipelines are running. Logs and progress updates appear below."
    SUCCESS_STATUS = "Pipelines finished successfully. Review the output below."
    FAILURE_STATUS = "Pipeline failed. Review the log and rerun if needed."

    def __init__(self, initial_message: str = "Running pipelines...") -> None:
        super().__init__()
        self.message = initial_message
        self._default_message = initial_message
        self._status_text = self.RUNNING_STATUS
        self._complete = False
        self._log_lines: list[str] = [initial_message] if initial_message else []
        self._current_line = ""
        self._rewrite_line = ""
        self._rewrite_visible = False
        self._in_rewrite = False
        self._pending_cr = False
        self._pipeline_callable: Callable[[], str] | None = None
        self._run_task: asyncio.Task | None = None
        self._rerun_visible = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(
            Static("Step 4/4 - Pipeline execution", classes="step-title"),
            Static(self._status_text, id="step4-status", classes="step-help"),
            TextLog(
                id="run-log",
                classes="panel",
                highlight=False,
                markup=False,
                wrap=True,
            ),
            Horizontal(
                Button("Rerun", id="rerun-step4", variant="warning", disabled=True),
                Button("Close", id="finish-step4", variant="primary", disabled=not self._complete),
                classes="step-actions",
            ),
            id="step-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._render_log()
        self._set_status_text(self._status_text)
        finish_btn = self.query_one("#finish-step4", Button)
        finish_btn.disabled = not self._complete
        self._apply_rerun_visibility()

    def start_run(self, pipeline_callable: Callable[[], str] | None = None) -> None:
        if pipeline_callable is not None:
            self._pipeline_callable = pipeline_callable
        if self._pipeline_callable is None:
            raise RuntimeError("No pipeline callable provided for StepFourScreen.")
        if self._run_task and not self._run_task.done():
            self._run_task.cancel()
        self._prepare_for_run()
        textual_app: "ToolManagerApp" = self.app  # type: ignore[assignment]
        screen = self

        class ScreenLogWriter(io.TextIOBase):
            def __init__(self) -> None:
                self._owner = textual_app
                self._screen = screen

            def write(self, data: str) -> int:  # pragma: no cover - Textual integration
                if not data:
                    return 0
                try:
                    self._owner.call_from_thread(self._screen.append_log, data)
                except RuntimeError:
                    return len(data)
                return len(data)

            def flush(self) -> None:  # pragma: no cover - Textual integration
                try:
                    self._owner.call_from_thread(self._screen.flush_pending_log)
                except RuntimeError:
                    pass

        log_writer = ScreenLogWriter()

        async def runner() -> None:
            success = True
            message = ""
            try:
                def run_with_capture() -> str:
                    with redirect_stdout(log_writer), redirect_stderr(log_writer):
                        return self._pipeline_callable()  # type: ignore[misc]

                message = await asyncio.to_thread(run_with_capture)
            except Exception as exc:  # pragma: no cover - runtime safeguard
                success = False
                message = f"Pipeline failed: {exc}"
            finally:
                try:
                    log_writer.flush()
                except RuntimeError:
                    pass
            screen.mark_complete(message, success)

        self._run_task = asyncio.create_task(runner())

    def append_log(self, text: str) -> None:
        if not text:
            return
        for char in text:
            if self._pending_cr:
                if char == "\n":
                    self._handle_newline()
                    self._pending_cr = False
                    continue
                self._start_rewrite()
                self._pending_cr = False
            if char == "\r":
                self._pending_cr = True
                continue
            if char == "\n":
                self._handle_newline()
                continue
            if self._in_rewrite:
                self._rewrite_line += char
            else:
                self._current_line += char
        if self._in_rewrite and self._rewrite_line:
            self._commit_rewrite_line(final=False)

    def flush_pending_log(self) -> None:
        if self._pending_cr:
            pass
        if self._in_rewrite and self._rewrite_line:
            self._commit_rewrite_line(final=False)
        if self._current_line:
            self._commit_current_line()

    def _write_line(self, line: str, *, replace: bool = False) -> None:
        if replace and self._log_lines:
            self._log_lines[-1] = line
        else:
            self._log_lines.append(line)
        if not self.is_mounted:
            return
        log = self.query_one("#run-log", TextLog)
        if replace:
            if hasattr(log, "clear"):
                log.clear()
            else:  # pragma: no cover - defensive fallback
                for child in list(log.children):
                    child.remove()
            for existing in self._log_lines:
                log.write(existing)
        else:
            log.write(line)

    def _render_log(self) -> None:
        log = self.query_one("#run-log", TextLog)
        if hasattr(log, "clear"):
            log.clear()
        else:  # pragma: no cover - defensive fallback
            for child in list(log.children):
                child.remove()
        for line in self._log_lines:
            log.write(line)

    def _start_rewrite(self) -> None:
        if self._current_line:
            self._commit_current_line()
        if self._in_rewrite and self._rewrite_line:
            self._commit_rewrite_line(final=False)
        self._in_rewrite = True
        self._rewrite_line = ""
        self._current_line = ""

    def _handle_newline(self) -> None:
        if self._in_rewrite:
            self._commit_rewrite_line(final=True)
        else:
            self._commit_current_line(force=True)

    def _commit_rewrite_line(self, *, final: bool) -> None:
        if not self._rewrite_line:
            if final:
                self._in_rewrite = False
                self._rewrite_visible = False
            return
        self._write_line(self._rewrite_line, replace=self._rewrite_visible)
        self._rewrite_line = ""
        if final:
            self._in_rewrite = False
            self._rewrite_visible = False
        else:
            self._rewrite_visible = True

    def _commit_current_line(self, *, force: bool = False) -> None:
        if not self._current_line and not force:
            return
        self._write_line(self._current_line, replace=False)
        self._current_line = ""

    def _prepare_for_run(self) -> None:
        self._complete = False
        self._rerun_visible = False
        self._set_status_text(self.RUNNING_STATUS)
        self._reset_log_state(self._default_message)
        if self.is_mounted:
            finish_btn = self.query_one("#finish-step4", Button)
            finish_btn.disabled = True
            self._apply_rerun_visibility()

    def _reset_log_state(self, initial_message: str) -> None:
        self.message = initial_message
        self._log_lines = [initial_message] if initial_message else []
        self._current_line = ""
        self._rewrite_line = ""
        self._rewrite_visible = False
        self._in_rewrite = False
        self._pending_cr = False
        if self.is_mounted:
            self._render_log()

    def _set_status_text(self, text: str) -> None:
        self._status_text = text
        if self.is_mounted:
            status_label = self.query_one("#step4-status", Static)
            status_label.update(text)

    def _apply_rerun_visibility(self) -> None:
        if not self.is_mounted:
            return
        rerun_btn = self.query_one("#rerun-step4", Button)
        rerun_btn.disabled = not self._rerun_visible
        rerun_btn.styles.display = "block" if self._rerun_visible else "none"

    def mark_complete(self, message: str, success: bool) -> None:
        self.message = message
        if message:
            suffix = "" if message.endswith("\n") else "\n"
            self.append_log(f"{message}{suffix}")
        self.flush_pending_log()
        self._complete = True
        self._set_status_text(self.SUCCESS_STATUS if success else self.FAILURE_STATUS)
        if self.is_mounted:
            finish_btn = self.query_one("#finish-step4", Button)
            finish_btn.disabled = False
            self._rerun_visible = not success
            self._apply_rerun_visibility()

    @on(Button.Pressed, "#finish-step4")
    def handle_close(self) -> None:
        self.app.exit(self.message)

    @on(Button.Pressed, "#rerun-step4")
    def handle_rerun(self) -> None:
        self.start_run()
