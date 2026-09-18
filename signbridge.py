#!/usr/bin/env python3
"""
SIGNBRIDGE v0.2
Kurzsyntax + Package-Command-Registry + dauerhafter Wicht-Livetick + Debugging

Syntax:
    `echo Hallo
    `cd /tmp
    `ls
    `repeat 3 : echo "Hallo"

Der Wicht-Livetick bleibt dauerhaft an einer festen Stelle aktiv.
Während ein Befehl läuft, wird dort nur das Zeichen gewechselt.
"""

import ast
import importlib
import inspect
import json
import os
import shlex
import sys
import time
import traceback
import threading
import itertools


class SignBridge:
    # Zeichenfolge für den dauerhaften Wicht-Livetick.
    # Der Wicht bleibt an EINER Stelle; nur sein Zustand/Zeichen wechselt.
    WICHT_FRAMES = ("`", "'", ".", ",", "-", "_", "`", ".", "'")
    WICHT_INTERVAL = 0.12

    def __init__(self):
        self.commands = {}
        self.signs = {}
        self.reverse = {}
        self.next_sign = 0

        self.debug = True
        self.livetick = True

        self._tick_lock = threading.Lock()
        self._tick_stop = threading.Event()
        self._tick_thread = None
        self._status_text = "READY"

        self.register_builtin_commands()
        self.start_livetick()

    # ------------------------------------------------------------
    # WICHT-LIVETICK
    # ------------------------------------------------------------

    def start_livetick(self):
        if self._tick_thread and self._tick_thread.is_alive():
            return

        self._tick_stop.clear()
        self._tick_thread = threading.Thread(
            target=self._livetick_loop,
            name="signbridge-wicht",
            daemon=True,
        )
        self._tick_thread.start()

    def stop_livetick(self):
        self._tick_stop.set()
        if self._tick_thread:
            self._tick_thread.join(timeout=0.5)

        # Cursor unter die Statuszeile setzen.
        with self._tick_lock:
            sys.stdout.write("\r" + " " * 90 + "\r")
            sys.stdout.flush()

    def _livetick_loop(self):
        frames = itertools.cycle(self.WICHT_FRAMES)

        while not self._tick_stop.is_set():
            if self.livetick:
                symbol = next(frames)

                with self._tick_lock:
                    # Eine feste Terminal-Zeile / feste Position.
                    # Kein Trail, keine neue Zeile pro Frame.
                    text = f"\r[WICHT {symbol}] {self._status_text:<30}"
                    sys.stdout.write(text)
                    sys.stdout.flush()

            self._tick_stop.wait(self.WICHT_INTERVAL)

    def _set_status(self, status):
        self._status_text = str(status)

    def tick(self, sign, command, state="RUN"):
        if not self.livetick:
            return
        self._set_status(f"{state} {command}")

    def tick_done(self, sign, command, result=None):
        if not self.livetick:
            return
        self._set_status(f"DONE {command}")

    # ------------------------------------------------------------
    # COMMAND REGISTRY
    # ------------------------------------------------------------

    def allocate_sign(self, name):
        preferred = {
            "echo": "0",
            "cd": ">",
            "ls": ":",
            "import": "+",
            "loop": "&",
            "if": "'-",
            "print": ".",
            "sleep": "~",
        }

        if name in preferred and preferred[name] not in self.reverse:
            sign = preferred[name]
        else:
            candidates = (
                "abcdefghijklmnopqrstuvwxyz"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                "0123456789"
                "!$%=?^~-+.;'/"
            )

            sign = None
            while self.next_sign < len(candidates):
                candidate = candidates[self.next_sign]
                self.next_sign += 1

                if candidate not in self.reverse and candidate != "`":
                    sign = candidate
                    break

            if sign is None:
                raise RuntimeError("Keine freien Command-Zeichen mehr.")

        self.signs[name] = sign
        self.reverse[sign] = name
        return sign

    def register(self, name, function, description=""):
        if name not in self.signs:
            sign = self.allocate_sign(name)
        else:
            sign = self.signs[name]

        self.commands[name] = {
            "function": function,
            "description": description,
            "sign": sign,
        }

        return sign

    def register_builtin_commands(self):
        self.register("echo", self.cmd_echo, "Text ausgeben")
        self.register("cd", self.cmd_cd, "Arbeitsverzeichnis wechseln")
        self.register("ls", self.cmd_ls, "Verzeichnis anzeigen")
        self.register("pwd", self.cmd_pwd, "Arbeitsverzeichnis anzeigen")
        self.register("sleep", self.cmd_sleep, "Warten")
        self.register("print", self.cmd_echo, "Text ausgeben")

    # ------------------------------------------------------------
    # BUILTIN COMMANDS
    # ------------------------------------------------------------

    def cmd_echo(self, *args):
        text = " ".join(str(x) for x in args)
        print(text)
        return text

    def cmd_cd(self, path="."):
        os.chdir(os.path.expanduser(str(path)))
        return os.getcwd()

    def cmd_ls(self, path="."):
        entries = sorted(os.listdir(os.path.expanduser(str(path))))
        for entry in entries:
            print(entry)
        return entries

    def cmd_pwd(self):
        result = os.getcwd()
        print(result)
        return result

    def cmd_sleep(self, seconds=1):
        seconds = float(seconds)
        time.sleep(seconds)
        return seconds

    # ------------------------------------------------------------
    # PACKAGE IMPORT
    # ------------------------------------------------------------

    def import_package(self, package_name):
        module = importlib.import_module(package_name)
        count = 0

        for name, obj in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("_"):
                continue

            # Nur Funktionen registrieren, die wirklich aus dem Modul
            # selbst stammen.
            if getattr(obj, "__module__", None) != module.__name__:
                continue

            self.register(
                name,
                obj,
                f"{package_name}.{name}",
            )
            count += 1

        print(f"[PACKAGE] {package_name}: {count} Befehle registriert")
        return count

    # ------------------------------------------------------------
    # REGISTRY
    # ------------------------------------------------------------

    def save_registry(self, filename="signbridge.json"):
        data = {}

        for name, item in self.commands.items():
            data[name] = {
                "sign": item["sign"],
                "description": item["description"],
            }

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"[REGISTRY] gespeichert: {filename}")

    def show_registry(self):
        print("\nSIGNBRIDGE COMMAND MAP")
        print("-" * 56)

        for name, item in self.commands.items():
            print(
                f"{item['sign']:>3}  "
                f"{name:<18} "
                f"{item['description']}"
            )

        print("-" * 56)

    # ------------------------------------------------------------
    # ARGUMENTE
    # ------------------------------------------------------------

    def convert_arg(self, value):
        if value.lower() == "true":
            return True

        if value.lower() == "false":
            return False

        if value.lower() == "none":
            return None

        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value

    # ------------------------------------------------------------
    # EXECUTION
    # ------------------------------------------------------------

    def execute(self, command_name, args):
        if command_name not in self.commands:
            raise ValueError(f"Unbekannter Befehl: {command_name}")

        item = self.commands[command_name]
        function = item["function"]
        sign = item["sign"]

        converted = [self.convert_arg(arg) for arg in args]

        self.tick(sign, command_name, "RUN")
        start = time.perf_counter()

        try:
            result = function(*converted)
            elapsed = time.perf_counter() - start

            self.tick_done(sign, command_name, result)

            # Debug-Zeile unterhalb des Live-Ticks.
            with self._tick_lock:
                if self.debug:
                    print(
                        f"\n[DEBUG] {sign} -> "
                        f"{command_name}({converted}) "
                        f"=> {result!r} "
                        f"[{elapsed:.4f}s]"
                    )

            return result

        except Exception as exc:
            self.tick(sign, command_name, "ERROR")

            with self._tick_lock:
                print(f"\n[ERROR] {command_name}: {exc}")
                if self.debug:
                    traceback.print_exc()

            return None

    # ------------------------------------------------------------
    # PARSER
    # ------------------------------------------------------------

    def parse_line(self, line):
        """
        Syntax:
            `echo Hallo
            `0 Hallo
            `cd /tmp
            `: /tmp
        """
        line = line.strip()

        if not line or line.startswith("#"):
            return None

        if not line.startswith("`"):
            raise SyntaxError("Jeder ausführbare Befehl benötigt `")

        content = line[1:].strip()

        if not content:
            return None

        parts = shlex.split(content)

        if not parts:
            return None

        command = parts[0]
        args = parts[1:]

        if command in self.reverse:
            command = self.reverse[command]

        return command, args

    # ------------------------------------------------------------
    # DATEI-AUSFÜHRUNG
    # ------------------------------------------------------------

    def execute_file(self, filename):
        with open(filename, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for number, line in enumerate(lines, 1):
            try:
                parsed = self.parse_line(line)

                if parsed is None:
                    continue

                command, args = parsed

                if command == "repeat":
                    self.execute_repeat(args)
                else:
                    self.execute(command, args)

            except Exception as exc:
                with self._tick_lock:
                    print(f"\n[SYNTAX ERROR] Zeile {number}: {exc}")

    def execute_repeat(self, args):
        if len(args) < 3:
            raise SyntaxError(
                "repeat benötigt: Anzahl Zeichen Befehl ..."
            )

        count = int(args[0])
        sign = args[1]
        command = self.reverse.get(sign, sign)
        command_args = args[2:]

        for _ in range(count):
            self.execute(command, command_args)

    # ------------------------------------------------------------
    # CLEANUP
    # ------------------------------------------------------------

    def close(self):
        self.stop_livetick()


def main():
    bridge = SignBridge()

    try:
        if len(sys.argv) < 2:
            print("SIGNBRIDGE v0.2")
            print()
            print("Verwendung:")
            print("  python3 signbridge.py map")
            print("  python3 signbridge.py import math")
            print("  python3 signbridge.py run program.sb")
            print("  python3 signbridge.py shell")
            return

        mode = sys.argv[1]

        if mode == "map":
            bridge.show_registry()

        elif mode == "import":
            if len(sys.argv) < 3:
                print("Package fehlt")
                return

            bridge.import_package(sys.argv[2])
            bridge.save_registry()
            bridge.show_registry()

        elif mode == "run":
            if len(sys.argv) < 3:
                print("Datei fehlt")
                return

            bridge.execute_file(sys.argv[2])

        elif mode == "shell":
            bridge.show_registry()

            print("\nSIGNBRIDGE SHELL")
            print("Beispiel: `echo Hallo")
            print("Beenden: exit\n")

            while True:
                try:
                    # Die Eingabe bleibt unterhalb des permanenten Wichts.
                    with bridge._tick_lock:
                        line = input("SB> ")

                    if line.strip() == "exit":
                        break

                    parsed = bridge.parse_line(line)

                    if parsed:
                        command, args = parsed
                        bridge.execute(command, args)

                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                except Exception as exc:
                    with bridge._tick_lock:
                        print(f"\n[ERROR] {exc}")

        else:
            print(f"Unbekannter Modus: {mode}")

    finally:
        bridge.close()


if __name__ == "__main__":
    main()
