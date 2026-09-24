import ast
import ast as _ast
from dataclasses import dataclass
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
import hashlib

ANSI_RESET = "\x1b[0m"
ANSI_COLORS = [30, 31, 32, 33, 34, 35, 36, 37]


def color_for_sign(sign):
    h = hashlib.sha1(sign.encode()).digest()[0]
    color = ANSI_COLORS[h % len(ANSI_COLORS)]
    return f"\x1b[1;{color}m"


@dataclass
class Command:
    function: callable
    description: str = ""
    sign: str = ""


class SignBridge:
    WICHT_FRAMES = ("`", "'", ".", ",", "-", "_", "`", ".", "'")
    WICHT_INTERVAL = 0.12
    WICHT_INTERVAL_MIN = 0.06
    WICHT_INTERVAL_MAX = 0.35

    def __init__(self):
        self.commands = {}
        self.signs = {}
        self.reverse = {}
        self.next_sign = 0

        self.debug = True
        self.livetick = True
        self.persist_wicht = True
        # configurable behavior: read from env or defaults
        self.random_wicht = True
        self.WICHT_INTERVAL_MIN = float(os.environ.get("WICHT_INTERVAL_MIN", self.WICHT_INTERVAL_MIN))
        self.WICHT_INTERVAL_MAX = float(os.environ.get("WICHT_INTERVAL_MAX", self.WICHT_INTERVAL_MAX))
        env_seed = os.environ.get("WICHT_SEED")
        if env_seed is not None:
            try:
                import random as _r
                _r.seed(int(env_seed))
                self._seed = int(env_seed)
            except Exception:
                self._seed = None
        else:
            self._seed = None

        self._tick_lock = threading.Lock()
        self._tick_stop = threading.Event()
        self._tick_thread = None
        self._status_text = "READY"
        self._current_wicht_symbol = None

        self.register_builtin_commands()
        self.start_livetick()

    # livetick
    def start_livetick(self):
        if self._tick_thread and self._tick_thread.is_alive():
            return
        self._tick_stop.clear()
        self._tick_thread = threading.Thread(target=self._livetick_loop, name="signbridge-wicht", daemon=True)
        self._tick_thread.start()

    def stop_livetick(self):
        if self.persist_wicht:
            return
        self._tick_stop.set()
        if self._tick_thread:
            self._tick_thread.join(timeout=0.5)
        with self._tick_lock:
            sys.stdout.write("\r" + " " * 90 + "\r")
            sys.stdout.flush()

    def _livetick_loop(self):
        import random
        while not self._tick_stop.is_set():
            if self.livetick:
                # choose a new random symbol each tick (no repeating cycle)
                if self.random_wicht:
                    symbol = random.choice(self.WICHT_FRAMES)
                else:
                    # deterministic progression using cycle when randomness disabled
                    try:
                        symbol = next(self._frames_iter)
                    except Exception:
                        self._frames_iter = itertools.cycle(self.WICHT_FRAMES)
                        symbol = next(self._frames_iter)
                with self._tick_lock:
                    # record current symbol for external extraction
                    self._current_wicht_symbol = symbol
                    text = f"\r[WICHT {symbol}] {self._status_text:<30}"
                    sys.stdout.write(text)
                    sys.stdout.flush()
            # randomize interval between ticks
            import random as _r
            interval = _r.uniform(self.WICHT_INTERVAL_MIN, self.WICHT_INTERVAL_MAX)
            self._tick_stop.wait(interval)

    # Wicht helpers
    def get_current_wicht(self):
        """Return the last symbol displayed by the Wicht (or None)."""
        return self._current_wicht_symbol

    def export_current_wicht(self, filename="current_wicht.txt"):
        """Export the current Wicht symbol and interval info to a text file."""
        sym = self.get_current_wicht()
        color = color_for_sign(sym) if sym else ""
        data = {
            "symbol": sym,
            "color_ansi": color,
            "interval_min": self.WICHT_INTERVAL_MIN,
            "interval_max": self.WICHT_INTERVAL_MAX,
            "status": self._status_text,
        }
        with open(filename, "w", encoding="utf-8") as f:
            for k, v in data.items():
                f.write(f"{k}: {v}\n")
        return filename

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

    # registry
    def allocate_sign(self, name):
        preferred = {"echo": "0", "cd": ">", "ls": ":", "import": "+", "loop": "&", "if": "'-", "print": ".", "sleep": "~"}
        if name in preferred and preferred[name] not in self.reverse:
            sign = preferred[name]
        else:
            candidates = ("abcdefghijklmnopqrstuvwxyz" "ABCDEFGHIJKLMNOPQRSTUVWXYZ" "0123456789" "!$%=?^~-+.;'/")
            sign = None
            for i in range(self.next_sign, len(candidates)):
                candidate = candidates[i]
                if candidate not in self.reverse and candidate != "`":
                    sign = candidate
                    self.next_sign = i + 1
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
        self.commands[name] = Command(function=function, description=description, sign=sign)
        return sign

    def register_builtin_commands(self):
        builtins = [("echo", self.cmd_echo, "Text ausgeben"), ("cd", self.cmd_cd, "Arbeitsverzeichnis wechseln"), ("ls", self.cmd_ls, "Verzeichnis anzeigen"), ("pwd", self.cmd_pwd, "Arbeitsverzeichnis anzeigen"), ("sleep", self.cmd_sleep, "Warten"), ("print", self.cmd_echo, "Text ausgeben")]
        for name, fn, desc in builtins:
            self.register(name, fn, desc)

    # builtins
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

    # import package
    def import_package(self, package_name):
        module = importlib.import_module(package_name)
        count = 0
        for name, obj in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("_"):
                continue
            if getattr(obj, "__module__", None) != module.__name__:
                continue
            self.register(name, obj, f"{package_name}.{name}")
            count += 1
        print(f"[PACKAGE] {package_name}: {count} Befehle registriert")
        return count

    # registry helpers
    def save_registry(self, filename="signbridge.json"):
        data = {}
        for name, item in self.commands.items():
            data[name] = {"sign": item.sign, "description": item.description}
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[REGISTRY] gespeichert: {filename}")

    def show_registry(self):
        print("\nSIGNBRIDGE COMMAND MAP")
        print("-" * 56)
        for name, item in self.commands.items():
            print(f"{item.sign:>3}  {name:<18} {item.description}")
        print("-" * 56)

    # args conversion & execution
    def convert_arg(self, value):
        if isinstance(value, str):
            v = value.strip()
            if v.lower() == "true":
                return True
            if v.lower() == "false":
                return False
            if v.lower() == "none":
                return None
            try:
                return ast.literal_eval(value)
            except Exception:
                return value
        return value

    def execute(self, command_name, args):
        if command_name not in self.commands:
            raise ValueError(f"Unbekannter Befehl: {command_name}")
        item = self.commands[command_name]
        function = item.function
        sign = item.sign
        converted = [self.convert_arg(arg) for arg in args]
        self.tick(sign, command_name, "RUN")
        start = time.perf_counter()
        try:
            result = function(*converted)
            elapsed = time.perf_counter() - start
            self.tick_done(sign, command_name, result)
            with self._tick_lock:
                if self.debug:
                    print(f"\n[DEBUG] {sign} -> {command_name}({converted}) => {result!r} [{elapsed:.4f}s]")
            return result
        except Exception as exc:
            self.tick(sign, command_name, "ERROR")
            with self._tick_lock:
                print(f"\n[ERROR] {command_name}: {exc}")
                if self.debug:
                    traceback.print_exc()
            return None

    # parser + file execution
    def parse_line(self, line):
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
            raise SyntaxError("repeat benötigt: Anzahl Zeichen Befehl ...")
        count = int(args[0])
        sign = args[1]
        command = self.reverse.get(sign, sign)
        command_args = args[2:]
        for _ in range(count):
            self.execute(command, command_args)

    def close(self):
        if not self.persist_wicht:
            self.stop_livetick()


# --- Helper tools: commandfinder, programreader, shortener ---


def list_package_functions(pkg_name):
    mod = importlib.import_module(pkg_name)
    funcs = []
    for name, obj in inspect.getmembers(mod, lambda o: inspect.isfunction(o) or inspect.isbuiltin(o)):
        if name.startswith("_"):
            continue
        if getattr(obj, "__module__", None) != mod.__name__:
            continue
        try:
            sig = str(inspect.signature(obj))
        except Exception:
            sig = "()"
        funcs.append((name, sig))
    return funcs


def print_program_parsed(filename):
    bridge = SignBridge()
    with open(filename, "r", encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            parsed = bridge.parse_line(line)
            if parsed is None:
                continue
            command, args = parsed
            print(f"{n:3}: {command} {args}")


def shorten_file(infile, outfile, frames=None, random_frames=False):
    bridge = SignBridge()
    if frames:
        bridge.WICHT_FRAMES = tuple(frames)
    with open(infile, "r", encoding="utf-8") as fin, open(outfile, "w", encoding="utf-8") as fout:
        for n, line in enumerate(fin, 1):
            ln = line.rstrip('\n')
            # py support: convert simple top-level calls
            if infile.endswith('.py'):
                try:
                    node = _ast.parse(ln)
                    if node.body and isinstance(node.body[0], _ast.Expr) and isinstance(node.body[0].value, _ast.Call):
                        call = node.body[0].value
                        func = call.func
                        if isinstance(func, _ast.Name):
                            command = func.id
                        elif isinstance(func, _ast.Attribute):
                            command = func.attr
                        else:
                            command = None
                        if command:
                            if '(' in ln and ')' in ln:
                                args_src = ln[ln.find('(')+1:ln.rfind(')')].strip()
                                args = [a.strip() for a in args_src.split(',')] if args_src else []
                            else:
                                args = []
                        else:
                            command = None
                    else:
                        command = None
                except Exception:
                    command = None
                if not command:
                    fout.write(line)
                    print(f" {n:3}: {ln}")
                    continue
            else:
                parsed = bridge.parse_line(ln)
                if not parsed:
                    fout.write(line)
                    print(f" {n:3}: {ln}")
                    continue
                command, args = parsed

            if command not in bridge.signs:
                bridge.register(command, lambda *a: None, description="auto")
            sign = bridge.signs.get(command, command)
            parts = shlex.split(ln.lstrip()[1:].strip()) if not infile.endswith('.py') else None
            new_content = " ".join([sign] + (parts[1:] if parts else args)) if (parts or args) else sign
            new_line = "`" + new_content + ("\n" if line.endswith("\n") else "")
            fout.write(new_line)
            c = color_for_sign(sign)
            preview = new_line.replace(sign, f"{c}{sign}{ANSI_RESET}", 1)
            print(f" {n:3}: {preview.rstrip()} -> {command} {args}")
            bridge.tick(sign, command, "SHORTEN")
    bridge.save_registry("signbridge.json")
    print(f"Shortened file written to: {outfile}")


def _color_code_from_hex(hexcode):
    # Accept formats like '#RRGGBB' and map to nearest ANSI color index
    if hexcode.startswith('#'):
        hexcode = hexcode[1:]
    try:
        r = int(hexcode[0:2], 16)
        g = int(hexcode[2:4], 16)
        b = int(hexcode[4:6], 16)
    except Exception:
        return ANSI_COLORS[0]
    idx = (r + g + b) % len(ANSI_COLORS)
    return ANSI_COLORS[idx]


def pack_file_to_symbol(filename, hexcolor=None):
    """Deterministically map file content to a single symbol and color, store mapping."""
    import base64
    if not os.path.exists(filename):
        raise FileNotFoundError(filename)
    with open(filename, 'rb') as f:
        data = f.read()
    # compress and encode to keep mapping small
    import zlib
    comp = zlib.compress(data, level=9)
    enc = base64.urlsafe_b64encode(comp).decode('ascii')
    # create a short hash to use as symbol (single unicode char from plane)
    h = hashlib.sha256(enc.encode()).digest()
    codepoint = 0x2500 + (h[0] << 8 | h[1]) % 0x1000  # box-drawing region
    symbol = chr(codepoint)
    color = None
    if hexcolor:
        color = _color_code_from_hex(hexcolor)
    else:
        color = ANSI_COLORS[h[2] % len(ANSI_COLORS)]

    meta = {'symbol': symbol, 'color': color, 'content_b64': enc}
    # write mapping file
    mappings = {}
    mapfile = 'file_signs.json'
    if os.path.exists(mapfile):
        try:
            with open(mapfile, 'r', encoding='utf-8') as mf:
                mappings = json.load(mf)
        except Exception:
            mappings = {}
    mappings[filename] = meta
    with open(mapfile, 'w', encoding='utf-8') as mf:
        json.dump(mappings, mf, indent=2)

    print(f"Packed {filename} -> symbol {symbol} (color {color})")
    return symbol, color


def unpack_symbol_to_file(filename, outpath):
    mapfile = 'file_signs.json'
    if not os.path.exists(mapfile):
        raise FileNotFoundError(mapfile)
    with open(mapfile, 'r', encoding='utf-8') as mf:
        mappings = json.load(mf)
    if filename not in mappings:
        raise KeyError(filename)
    enc = mappings[filename]['content_b64']
    import base64, zlib
    comp = base64.urlsafe_b64decode(enc.encode('ascii'))
    data = zlib.decompress(comp)
    with open(outpath, 'wb') as out:
        out.write(data)
    print(f"Unpacked {filename} -> {outpath}")


def main():
    # global options: allow configuring livetick behavior via env or flags
    # flags: --wicht-min X --wicht-max Y --wicht-seed N
    args = sys.argv[1:]
    # parse simple flags
    i = 0
    while i < len(args) and args[i].startswith("--"):
        flag = args[i]
        if flag == "--wicht-min" and i + 1 < len(args):
            os.environ["WICHT_INTERVAL_MIN"] = args[i + 1]
            i += 2
            continue
        if flag == "--wicht-max" and i + 1 < len(args):
            os.environ["WICHT_INTERVAL_MAX"] = args[i + 1]
            i += 2
            continue
        if flag == "--wicht-seed" and i + 1 < len(args):
            os.environ["WICHT_SEED"] = args[i + 1]
            i += 2
            continue
        break
    if i >= len(args):
        print(__doc__)
        return
    cmd = args[i]
    rest = args[i+1:]
    bridge = SignBridge()
    if cmd == "map":
        bridge.show_registry()
    elif cmd == "import":
        if len(sys.argv) < 3:
            print("Package fehlt")
            return
        bridge.import_package(sys.argv[2])
        bridge.save_registry()
        bridge.show_registry()
    elif cmd == "run":
        if len(sys.argv) < 3:
            print("Datei fehlt")
            return
        bridge.execute_file(sys.argv[2])
    elif cmd == "shell":
        bridge.show_registry()
        print("\nSIGNBRIDGE SHELL (all_in_one)")
        print("Beispiel: `echo Hallo")
        print("Beenden: exit\n")
        while True:
            try:
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
    elif cmd == "shorten":
        if len(sys.argv) < 3:
            print("Usage: all_in_one shorten input [output]")
            return
        infile = sys.argv[2]
        outfile = sys.argv[3] if len(sys.argv) >= 4 else infile + ".short.sb"
        shorten_file(infile, outfile)
    elif cmd == "find":
        if len(sys.argv) < 3:
            print("Usage: all_in_one find <package>")
            return
        pkg = sys.argv[2]
        try:
            funcs = list_package_functions(pkg)
        except Exception as e:
            print(f"Error importing {pkg}: {e}")
            return
        print(f"Package: {pkg} — {len(funcs)} functions")
        for name, sig in funcs:
            print(f"{name}{sig}")
    elif cmd == "read":
        if len(sys.argv) < 3:
            print("Usage: all_in_one read <file>")
            return
        print_program_parsed(sys.argv[2])
    elif cmd == "pack":
        if len(sys.argv) < 2:
            print("Usage: all_in_one pack <file> [hexcolor]")
            return
        fname = sys.argv[2]
        hexc = sys.argv[3] if len(sys.argv) >= 4 else None
        pack_file_to_symbol(fname, hexc)
    elif cmd == "unpack":
        if len(sys.argv) < 3:
            print("Usage: all_in_one unpack <orig_filename> <outpath>")
            return
        unpack_symbol_to_file(sys.argv[2], sys.argv[3])
    else:
        print(f"Unbekannter Modus: {cmd}")


if __name__ == "
    main()
