"""Standalone Wicht live status indicator.

The Wicht displays a small animated status line while work is running.  It is
independent from SignBridge and can be used by any command-line program.
"""

from __future__ import annotations

import hashlib
import itertools
import os
import random
import sys
import threading
from pathlib import Path
from typing import Optional, TextIO


ANSI_RESET = "\x1b[0m"
ANSI_COLORS = (30, 31, 32, 33, 34, 35, 36, 37)


def color_for_symbol(symbol: str) -> str:
    """Return a stable ANSI bold color escape sequence for *symbol*."""
    digest = hashlib.sha1(symbol.encode("utf-8")).digest()[0]
    return f"\x1b[1;{ANSI_COLORS[digest % len(ANSI_COLORS)]}m"


class Wicht:
    """A thread-based, terminal-friendly live status indicator.

    Parameters may be configured directly or through environment variables:
    ``WICHT_INTERVAL_MIN``, ``WICHT_INTERVAL_MAX`` and ``WICHT_SEED``.
    """

    FRAMES = ("`", "'", ".", ",", "-", "_", "`", ".", "'")
    DEFAULT_INTERVAL_MIN = 0.06
    DEFAULT_INTERVAL_MAX = 0.35

    def __init__(
        self,
        *,
        frames: tuple[str, ...] | list[str] | None = None,
        random_frames: bool = True,
        interval_min: float | None = None,
        interval_max: float | None = None,
        seed: int | None = None,
        enabled: bool = True,
        stream: TextIO | None = None,
    ) -> None:
        self.frames = tuple(frames or self.FRAMES)
        if not self.frames:
            raise ValueError("frames must contain at least one symbol")

        self.random_frames = random_frames
        self.interval_min = self._float_setting(
            interval_min, "WICHT_INTERVAL_MIN", self.DEFAULT_INTERVAL_MIN
        )
        self.interval_max = self._float_setting(
            interval_max, "WICHT_INTERVAL_MAX", self.DEFAULT_INTERVAL_MAX
        )
        if self.interval_min < 0 or self.interval_max < self.interval_min:
            raise ValueError("intervals must satisfy 0 <= interval_min <= interval_max")

        if seed is None and os.environ.get("WICHT_SEED") is not None:
            try:
                seed = int(os.environ["WICHT_SEED"])
            except ValueError:
                seed = None

        self.enabled = enabled
        self.stream = stream or sys.stdout
        self.status = "READY"
        self.current_symbol: Optional[str] = None

        self._random = random.Random(seed)
        self._frames = itertools.cycle(self.frames)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def _float_setting(value: float | None, name: str, default: float) -> float:
        if value is not None:
            return float(value)
        return float(os.environ.get(name, default))

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        """Start the background ticker; repeated calls are harmless."""
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="wicht", daemon=True
        )
        self._thread.start()

    def stop(self, *, clear: bool = True) -> None:
        """Stop the ticker and optionally clear its terminal line."""
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=max(self.interval_max, 0.5) + 0.1)
        if clear:
            self._write("\r" + " " * 90 + "\r")

    def close(self) -> None:
        """Alias for :meth:`stop`, suitable for cleanup handlers."""
        self.stop()

    def __enter__(self) -> "Wicht":
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.stop()

    def set_status(self, status: object) -> None:
        """Update the text shown beside the current symbol."""
        with self._lock:
            self.status = str(status)

    def tick(self, state: str = "RUN", command: str = "") -> None:
        """Set a conventional ``STATE command`` status."""
        self.set_status(f"{state} {command}".rstrip())

    def get_current(self) -> Optional[str]:
        """Return the most recently displayed symbol."""
        with self._lock:
            return self.current_symbol

    def export(self, filename: str | os.PathLike[str] = "current_wicht.txt") -> str:
        """Write the current symbol and configuration to a text file."""
        with self._lock:
            symbol = self.current_symbol
            status = self.status
        data = {
            "symbol": symbol,
            "color_ansi": color_for_symbol(symbol) if symbol else "",
            "interval_min": self.interval_min,
            "interval_max": self.interval_max,
            "status": status,
        }
        path = Path(filename)
        path.write_text("".join(f"{key}: {value}\n" for key, value in data.items()), encoding="utf-8")
        return str(path)

    def _next_symbol(self) -> str:
        if self.random_frames:
            return self._random.choice(self.frames)
        return next(self._frames)

    def _run(self) -> None:
        while not self._stop.is_set():
            if self.enabled:
                symbol = self._next_symbol()
                with self._lock:
                    self.current_symbol = symbol
                    status = self.status
                self._write(f"\r[WICHT {symbol}] {status:<30}")
            interval = self._random.uniform(self.interval_min, self.interval_max)
            self._stop.wait(interval)

    def _write(self, text: str) -> None:
        with self._lock:
            self.stream.write(text)
            self.stream.flush()


if __name__ == "__main__":
    import time

    with Wicht() as wicht:
        for state in ("READY", "RUN demo", "DONE demo"):
            wicht.set_status(state)
            time.sleep(1)
