"""wbuild: an interactive shell with a live Wicht status indicator.

Run::

    python wbuild.py

The shell keeps the Wicht ticker active while commands are entered. Type
``help`` to see supported commands and ``exit`` or ``quit`` to leave.
"""

from __future__ import annotations

import argparse
import shlex
import sys
import time
from typing import Callable

from wicht import Wicht


class WBuildShell:
    """Small command shell whose activity is shown by a :class:`Wicht`."""

    def __init__(self, wicht: Wicht | None = None) -> None:
        self.wicht = wicht or Wicht()
        self._commands: dict[str, Callable[[list[str]], bool]] = {
            "help": self._help,
            "status": self._status,
            "start": self._start,
            "stop": self._stop,
            "export": self._export,
            "sleep": self._sleep,
            "clear": self._clear,
            "exit": self._exit,
            "quit": self._exit,
        }
        self._running = True

    def run(self) -> int:
        """Run the interactive shell until the user exits."""
        self.wicht.start()
        self.wicht.set_status("READY")
        self._write("wbuild shell — Wicht is active; type 'help' for commands")
        try:
            while self._running:
                try:
                    line = input("\nwbuild> ")
                except (EOFError, KeyboardInterrupt):
                    self._write("\n")
                    break
                self.execute(line)
        finally:
            self.wicht.stop()
        return 0

    def execute(self, line: str) -> None:
        """Parse and execute one shell line."""
        try:
            parts = shlex.split(line)
        except ValueError as exc:
            self._error(f"parse error: {exc}")
            return
        if not parts:
            return

        name, args = parts[0].lower(), parts[1:]
        command = self._commands.get(name)
        if command is None:
            self.wicht.tick("ERROR", name)
            self._error(f"unknown command: {name!r}; try 'help'")
            return
        try:
            self.wicht.tick("RUN", name)
            should_continue = command(args)
            if not should_continue:
                self._running = False
            if name not in {"start", "stop", "exit", "quit"}:
                self.wicht.tick("READY")
        except Exception as exc:  # keep the interactive shell alive
            self.wicht.tick("ERROR", name)
            self._error(str(exc))

    def _help(self, _args: list[str]) -> bool:
        self._write(
            "Commands:\n"
            "  help                  show this help\n"
            "  status                show Wicht state\n"
            "  start / stop          control the live indicator\n"
            "  export [file]         save current Wicht state\n"
            "  sleep SECONDS         wait while showing activity\n"
            "  clear                 clear the terminal\n"
            "  exit / quit           leave wbuild"
        )
        return True

    def _status(self, _args: list[str]) -> bool:
        symbol = self.wicht.get_current()
        self._write(
            f"Wicht: {'running' if self.wicht.running else 'stopped'} | "
            f"symbol={symbol!r} | status={self.wicht.status!r}"
        )
        return True

    def _start(self, _args: list[str]) -> bool:
        self.wicht.start()
        self._write("Wicht started")
        return True

    def _stop(self, _args: list[str]) -> bool:
        self.wicht.stop()
        self._write("Wicht stopped")
        return True

    def _export(self, args: list[str]) -> bool:
        filename = args[0] if args else "current_wicht.txt"
        self._write(f"Wicht state exported to {self.wicht.export(filename)}")
        return True

    def _sleep(self, args: list[str]) -> bool:
        if len(args) != 1:
            raise ValueError("usage: sleep SECONDS")
        seconds = float(args[0])
        self.wicht.set_status(f"SLEEP {seconds:g}s")
        time.sleep(seconds)
        self._write(f"slept for {seconds:g}s")
        return True

    def _clear(self, _args: list[str]) -> bool:
        self._write("\033[2J\033[H", end="")
        return True

    def _exit(self, _args: list[str]) -> bool:
        self.wicht.set_status("EXIT")
        return False

    @staticmethod
    def _write(message: str, *, end: str = "\n") -> None:
        sys.stdout.write(message + end)
        sys.stdout.flush()

    @staticmethod
    def _error(message: str) -> None:
        sys.stderr.write(f"wbuild: {message}\n")
        sys.stderr.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="wbuild shell with a Wicht ticker")
    parser.add_argument("--min", type=float, dest="interval_min", help="minimum tick interval")
    parser.add_argument("--max", type=float, dest="interval_max", help="maximum tick interval")
    parser.add_argument("--seed", type=int, help="seed for repeatable Wicht frames")
    parser.add_argument("--deterministic", action="store_true", help="cycle through frames instead of random selection")
    args = parser.parse_args(argv)

    wicht = Wicht(
        interval_min=args.interval_min,
        interval_max=args.interval_max,
        seed=args.seed,
        random_frames=not args.deterministic,
    )
    return WBuildShell(wicht).run()


if __name__ == "__main__":
    raise SystemExit(main())


# EOF
