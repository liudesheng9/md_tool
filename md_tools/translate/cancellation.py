from __future__ import annotations

import threading


class TranslationCancelled(Exception):
    """Raised when a translation run has been cancelled."""


class TranslationCancelToken:
    """Thread-safe cancellation token shared between translation workers."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float) -> bool:
        """Wait for cancellation or timeout. Returns True when cancelled."""

        if timeout <= 0:
            return self.is_cancelled()
        return self._event.wait(timeout)

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise TranslationCancelled()

