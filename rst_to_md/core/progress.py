"""Lightweight, dependency-free live progress tracker.

The tracker renders a single in-place status line to stderr when attached to a
terminal (TTY). In non-interactive contexts (CI, piped output) it stays silent
so logs and the ``--report`` JSON remain machine-readable.

Example rendered line::

    Converting 12/50 | 3.4s | ok 10 err 1 skip 1 | 3.5/s
"""

from __future__ import annotations

import sys
import time
from typing import TextIO


class ProgressTracker:
    """Track conversion progress and render a live status line on a TTY.

    Counters are always maintained (so callers can summarise even when silent);
    only the on-screen rendering is gated by ``enabled`` *and* a TTY check.
    """

    def __init__(
        self,
        total: int,
        *,
        enabled: bool = True,
        stream: TextIO = sys.stderr,
        desc: str = "Converting",
    ) -> None:
        self.total = total
        self.stream: TextIO = stream
        self.desc = desc
        self.enabled = bool(enabled) and getattr(stream, "isatty", lambda: False)()
        self.count = 0
        self.ok = 0
        self.err = 0
        self.skip = 0
        self._start: float | None = None

    def start(self) -> None:
        """Begin timing and draw the initial (empty) bar."""
        if self.enabled:
            self._start = time.monotonic()
            self._render()

    def update(self, status: str, msg: str = "") -> None:
        """Record one completed file and refresh the display.

        ``status`` is one of ``"ok"``, ``"error"``, ``"skipped"``. When an error
        occurs and ``msg`` is provided, the message is printed above the bar so
        the user sees *why* a file failed without waiting for the summary.
        """
        self.count += 1
        if status == "ok":
            self.ok += 1
        elif status == "error":
            self.err += 1
        elif status == "skipped":
            self.skip += 1

        if not self.enabled:
            return
        if status == "error" and msg:
            self._write_line(f"  ! {msg}")
        else:
            self._render()

    def _elapsed(self) -> float:
        if self._start is None:
            return 0.0
        return time.monotonic() - self._start

    def _render(self) -> None:
        elapsed = self._elapsed()
        rate = self.count / elapsed if elapsed > 0 else 0.0
        line = (
            f"{self.desc} {self.count}/{self.total} | "
            f"{elapsed:.1f}s | ok {self.ok} err {self.err} skip {self.skip} | "
            f"{rate:.1f}/s"
        )
        # \r returns to column 0; \033[K clears to end-of-line (handles shrink).
        self.stream.write("\r\033[K" + line)
        self.stream.flush()

    def _write_line(self, text: str) -> None:
        # Clear the bar, print the message on its own line, then redraw the bar.
        self.stream.write("\r\033[K" + text + "\n")
        self._render()

    def finish(self) -> None:
        """Finalise: move to a fresh line so subsequent logs are clean."""
        if self.enabled:
            self.stream.write("\n")
            self.stream.flush()
