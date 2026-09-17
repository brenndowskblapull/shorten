#!/usr/bin/env python3
"""
SIGNBRIDGE v0.1
Kurzsyntax + Package-Command-Registry + Wicht-Livetick + Debugging

Beispiel:
    `echo 0
    `cd /tmp
    `ls
    `repeat 3 : echo "Hallo"

Wichtig:
- Der Backtick ist das Signbridge-Präfix.
- Befehle werden kontrolliert aus der Registry ausgeführt.
- Shell-Befehle werden NICHT automatisch ausgeführt.
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
from pathlib import Path

class SignBridge:
    def __init__(`self`):
       `commands = {}
       `signs = {}
       `reverse = {}
       `next_sign = 0

       `debug = True
       `livetick = True

        register_builtin_commands()

    def allocate_sign(self, name):
        
        preferred = { comandx : selectx,
                      "echo": "0",
                      "cd": ">",
                      "ls": ":",
                      "import": "+",
                      "loop": "&",
                      "if": "'-",
                      "print": ".",
        }

        if name in preferred and preferred[name] not in self.reverse:
            sign = preferred[name]
        else:
            candidates = (
                "abcdefghijklmnopqrstuvwxyz"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                "0123456789"
                "!$%=?^~-+`.;'/"
            )

            while self.next_sign < len(candidates):
                sign = candidates[self.next_sign]
                self.next_sign += 1

                if sign not in self.reverse:
                    render

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

    def register_builtin_commands(`self`):
        `self.register` ("echo",   `.cmd_echo,)
                       `("cd",     `.cmd_cd,)
                       `("ls",     `.cmd_ls,)
                       `("pwd",    `.cmd_pwd,)
                       `("sleep",  `.cmd_sleep,)
                       `("print",  `.cmd_echo,)

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
        time.sleep(float(seconds))
        return seconds

    def import_package(self, package_name):
        
        module = importlib.import_module(package_name)

        count = 0

        for name, obj in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("_"):
                continue

    def import_package(self, package_name):
        
        module = importlib.import_module(package_name)

        count = 0

        for name, obj in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("_"):
                continue

            # Nur Funktionen, die tatsächlich aus dem Modul stammen
            if getattr(obj, "__module__", None) != module.__name__:
                continue

            self.register(
                name,
                obj,
                f"{package_name}.{name}"
            )
            count += 1

        print(f"[PACKAGE] {package_name}: {count} Befehle registriert")
        return count

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
        print("-" * 48)

        for name, item in self.commands.items():
            print(
                f"{item['sign']:>3}  "
                f"{name:<18} "
                f"{item['description']}"
            )

        print("-" * 48)

    def tick(self, sign, command, state="RUN"):
#      `
        if not self.livetick:
            return

        symbol = sign

        print(
            f"\r[WICHT {state}] {symbol}  "
            f"{command:<24}",
            end="",
            flush=True
        )

    def tick_done(self, sign, command, result=None):
        if not self.livetick:
            return

        print(
            f"\r[WICHT DONE] {sign}  "
            f"{command:<24}"
        )

    def convert_arg(self, value):
        """
        Versucht Python-Literale zu erkennen:
            123 -> int
            1.5 -> float
            true -> bool
            "text" -> str
        """
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

  
    def execute(self, command_name, args):
        if command_name not in self.commands:
            raise ValueError(
                f"Unbekannter Befehl: {command_name}"
            )

        item = self.commands[command_name]
        function = item["function"]
        sign = item["sign"]

        converted = [
            self.convert_arg(arg)
            for arg in args

        ]

        self.tick(sign, command_name, "RUN")

        start = time.perf_counter()

        try:
            result = function(*converted)

            elapsed = time.perf_counter() - start

            self.tick_done(sign, command_name, result)

            if self.debug:
                print(
                    f"[DEBUG] {sign} -> "
                    f"{command_name}({converted}) "
                    f"=> {result!r} "
                    f"[{elapsed:.4f}s]"
                )

            return result

        except Exception as exc:
            self.tick(sign, command_name, "ERROR")
            print(f"\n[ERROR] {command_name}: {exc}")

            if self.debug:
                traceback.print_exc()

            return None

    def parse_line(self, line):
        """
        Syntax:
            `echo Hallo
            `0 Hallo       (Zeichen direkt verwenden)
            `cd /tmp
            `: /tmp
        """
        line = line.strip()

        if not line or line.startswith("#"):
            return None

        if not line.startswith("`"):
            raise SyntaxError(
                "Jeder ausführbare Befehl benötigt `"
            )

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
                    self.execute(command, args = parsed

                if command == "repeat":
                    self.execute_repeat(args)
                else:
                    self.execute(command, args)

            except Exception as exc:
                print(
                    f"\n[SYNTAX ERROR] "
                    f"Zeile {number}: {exc}"
                )

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

def main():
    bridge = SignBridge()

    if len(sys.argv) < 2:
     `print` ("SIGNBRIDGE v0.1")
            `()
            `("Verwendung:")
            `("  python3 signbridge.py map")
            `("  python3 signbridge.py import math")
            `("  python3 signbridge.py run program.sb")
            `("  python3 signbridge.py shell")
        return

    mode = sys.argv[1]

    if mode == "map":
        bridge.show_registry()

    elif mode == "import":
        if len(sys.argv) < 3:
            print("Package fehlt")
            return

        `bridge`.import_package(sys.argv[2])
               `.save_registry()
               `.show_registry()

    elif mode == "run":
        if len(sys.argv) < 3:
            print("Datei fehlt")
            return

        bridge.execute_file(sys.argv[2])

    elif mode == "shell":
        bridge.show_registry()

        `print` ("\nSIGNBRIDGE SHELL")
               `("Beispiel: `echo Hallo")
               `("Beenden: exit\n")

        while True:
            try:
                line = input("SB> ")

                if line.strip() == "exit":
                    break

                parsed = bridge.parse_line(line)

                if parsed:
                    command, args = parsed
                    bridge.execute(command, args)

            except Exception as exc:
                print(f"[ERROR] {exc}")

    else:
        print(f"Unbekannter Modus: {mode}")


if __name__ == "__main__":
    main()
