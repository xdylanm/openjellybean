#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate the openjellybean KiCad symbol libraries from tests/models.toml.

This script is MIT-licensed like the rest of the code, but its output is not. Every
device in ``tests/models.toml`` gets one symbol, with graphics and pins copied from
a stock KiCad symbol chosen by the device's ``kind``, so the generated files are
derivatives of the KiCad symbol libraries (CC-BY-SA 4.0 with the KiCad libraries
exception; see kicad/LICENSE.md). The ``Sim.*`` fields point KiCad's simulator at
``jellybean.lib`` and map symbol pins to the model's pins.

    python tools/gen_symbols.py                    # write kicad/symbols/*.kicad_sym
    python tools/gen_symbols.py --check            # fail if the committed files are stale
    python tools/gen_symbols.py --kicad-symbols D  # stock libraries in directory D

Standard library only. It needs a KiCad 9 symbol directory (the ``kicad-symbols``
package) as input, found via $KICAD_SYMBOL_DIR, $KICAD9_SYMBOL_DIR or the usual
install locations.
"""
from __future__ import annotations

import argparse
import copy
import difflib
import os
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from harness import parse_library  # noqa: E402  (stdlib-only SPICE library parser)

LIBRARY_FILE = ROOT / "jellybean.lib"
MODELS_TOML = ROOT / "tests" / "models.toml"
DEFAULT_OUT = ROOT / "kicad" / "symbols"

#: The path variable users set to the folder that holds jellybean.lib.
SIM_LIBRARY = "${OPENJELLYBEAN_DIR}/jellybean.lib"

#: Output library for each model kind.
LIBRARY_OF_KIND = {
    "npn": "OpenJellybean_BJT", "pnp": "OpenJellybean_BJT",
    "nmos": "OpenJellybean_FET", "pmos": "OpenJellybean_FET",
    "njfet": "OpenJellybean_FET", "pjfet": "OpenJellybean_FET",
    "diode": "OpenJellybean_Diode", "schottky": "OpenJellybean_Diode",
    "zener": "OpenJellybean_Diode", "led": "OpenJellybean_Diode",
    "opamp": "OpenJellybean_Amplifier", "opamp2": "OpenJellybean_Amplifier",
    "opamp4": "OpenJellybean_Amplifier",
}

#: Stock symbol (library, name) to copy for each kind, and a plain-English noun.
BASE = {
    "npn": ("Transistor_BJT", "Q_NPN_CBE", "NPN transistor"),
    "pnp": ("Transistor_BJT", "Q_PNP_CBE", "PNP transistor"),
    "nmos": ("Transistor_FET", "Q_NMOS_DGS", "N-channel MOSFET"),
    "pmos": ("Transistor_FET", "Q_PMOS_DGS", "P-channel MOSFET"),
    "njfet": ("Device", "Q_NJFET_DGS", "N-channel JFET"),
    "pjfet": ("Device", "Q_PJFET_DGS", "P-channel JFET"),
    "diode": ("Device", "D", "Diode"),
    "schottky": ("Device", "D_Schottky", "Schottky diode"),
    "zener": ("Device", "D_Zener", "Zener diode"),
    "led": ("Device", "LED", "LED"),
    "opamp": ("Simulation_SPICE", "OPAMP", "Op-amp, one section"),
    "opamp2": ("Amplifier_Operational", "LM2904", "Dual op-amp"),
    "opamp4": ("Amplifier_Operational", "LM2902", "Quad op-amp"),
}

#: KiCad's name for the device when the model is a .model statement.
SIM_DEVICE = {
    "npn": "NPN", "pnp": "PNP", "nmos": "NMOS", "pmos": "PMOS",
    "njfet": "NJFET", "pjfet": "PJFET",
    "diode": "D", "schottky": "D", "zener": "D", "led": "D",
}

PACKAGE_KINDS = ("opamp", "opamp2", "opamp4")  # pins are numbered like the SPICE nodes

#: Where the stock symbol libraries usually live.
STOCK_DIRS = (
    "/usr/share/kicad/symbols",
    "/usr/local/share/kicad/symbols",
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols",
    "C:/Program Files/KiCad/9.0/share/kicad/symbols",
)


# ------------------------------------------------------------ s-expressions --
_TOKEN = re.compile(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()"]+')


def parse(text):
    """Parse KiCad s-expression text into nested lists. Strings keep their quotes."""
    stack = [[]]
    for token in _TOKEN.findall(text):
        if token == "(":
            stack.append([])
        elif token == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(token)
    return stack[0][0]


def quote(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def unquote(token):
    return token[1:-1].replace('\\"', '"').replace("\\\\", "\\") if token.startswith('"') else token


def dump(node, depth=0):
    """Write a node the way KiCad does, roughly: tabs, one child list per line."""
    if not any(isinstance(c, list) for c in node):
        return "(" + " ".join(node) + ")"
    pad = "\t" * (depth + 1)
    head = " ".join(c for c in node if not isinstance(c, list))
    lines = ["(" + head]
    lines += [pad + dump(c, depth + 1) for c in node if isinstance(c, list)]
    lines.append("\t" * depth + ")")
    return "\n".join(lines)


def children(node, tag):
    return [c for c in node if isinstance(c, list) and c and c[0] == tag]


# ------------------------------------------------------------- stock input ---
class Stock:
    """Reads stock symbols on demand and resolves ``(extends ...)`` chains."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self._libs = {}

    def _load(self, library):
        if library not in self._libs:
            path = self.directory / f"{library}.kicad_sym"
            if not path.is_file():
                raise SystemExit(f"missing stock library {path}")
            root = parse(path.read_text(encoding="utf-8"))
            symbols = {unquote(s[1]): s for s in children(root, "symbol")}
            self._libs[library] = (root, symbols)
        return self._libs[library]

    def header(self, library="Device"):
        """(version, generator_version) of a stock library, to match its file format."""
        root, _ = self._load(library)
        version = children(root, "version")[0][1]
        gen = children(root, "generator_version")[0][1]
        return version, gen

    def symbol(self, library, name):
        """A deep copy of the stock symbol with any parent's graphics merged in."""
        _, symbols = self._load(library)
        if name not in symbols:
            raise SystemExit(f"stock symbol {library}:{name} not found")
        symbol = copy.deepcopy(symbols[name])
        extends = children(symbol, "extends")
        if extends:
            parent = self.symbol(library, unquote(extends[0][1]))
            own = {c[1] for c in children(symbol, "property")}
            symbol = [c for c in symbol if c not in extends]
            symbol += [p for p in children(parent, "property") if p[1] not in own]
            symbol += children(parent, "symbol")
            symbol += [c for c in parent[2:] if isinstance(c, list)
                       and c[0] not in ("property", "symbol", "extends")
                       and c[0] not in {x[0] for x in symbol[2:] if isinstance(x, list)}]
            # sub-symbols carry the parent's name; the caller renames them
            parent_name = unquote(parent[1])
            symbol = rename_units(symbol, parent_name, name)
        return symbol


def rename_units(symbol, old, new):
    """Rename sub-symbols from ``old_N_M`` to ``new_N_M``."""
    out = []
    for child in symbol:
        if isinstance(child, list) and child and child[0] == "symbol":
            unit = unquote(child[1])
            if unit.startswith(old + "_"):
                child = [child[0], quote(new + unit[len(old):])] + child[2:]
        out.append(child)
    return out


def pins_of(symbol):
    """[(number, name)] for every pin of the symbol and its units."""
    found = []

    def walk(node):
        for child in node:
            if isinstance(child, list):
                if child and child[0] == "pin":
                    number = unquote(children(child, "number")[0][1])
                    name = unquote(children(child, "name")[0][1])
                    found.append((number, name))
                else:
                    walk(child)

    walk(symbol)
    return found


# ------------------------------------------------------------ symbol build ---
def hidden_property(template, name, value):
    prop = copy.deepcopy(template)
    prop[1], prop[2] = quote(name), quote(value)
    effects = children(prop, "effects")[0]
    if not children(effects, "hide"):
        effects.append(["hide", "yes"])
    return prop


def sim_pins(kind, device, symbol_pins):
    """The ``Sim.Pins`` value: symbol pin number -> model pin name."""
    if kind in PACKAGE_KINDS:
        by_number = {str(i + 1): pin for i, pin in enumerate(device.pins)}
        return " ".join(f"{n}={by_number[n]}" for n in sorted({n for n, _ in symbol_pins}, key=int))
    names = {pin.lower(): pin for pin in device.pins} if device.statement == "subckt" else {}
    pairs = []
    for number, name in sorted(symbol_pins, key=lambda p: int(p[0])):
        pairs.append(f"{number}={names.get(name.lower(), name)}")
    return " ".join(pairs)


def build_symbol(stock, name, entry, device):
    kind = entry["kind"]
    library, base_name, noun = BASE[kind]
    symbol = stock.symbol(library, base_name)
    symbol = rename_units(symbol, base_name, name)
    symbol[1] = quote(name)

    stands_in = ", ".join(entry.get("stand_in_for", []))
    description = f"{noun}, openjellybean SPICE model" + (f", stands in for {stands_in}" if stands_in else "")
    keywords = " ".join(["SPICE", "simulation", "openjellybean", *entry.get("stand_in_for", [])])

    old_props = children(symbol, "property")
    template = next(p for p in old_props if p[1] == quote("Datasheet"))
    keep = {}
    for prop in old_props:
        key = unquote(prop[1])
        if key in ("Reference", "Value", "Footprint", "Datasheet"):
            keep[key] = prop
    keep["Value"][2] = quote(name)
    keep["Footprint"][2] = quote("")
    keep["Datasheet"][2] = quote("~")
    props = [keep["Reference"], keep["Value"], keep["Footprint"], keep["Datasheet"]]
    props.append(hidden_property(template, "Description", description))
    props.append(hidden_property(template, "ki_keywords", keywords))

    sim_device = "SUBCKT" if device.statement == "subckt" else SIM_DEVICE[kind]
    sim = [("Sim.Device", sim_device), ("Sim.Library", SIM_LIBRARY), ("Sim.Name", name),
           ("Sim.Pins", sim_pins(kind, device, pins_of(symbol)))]
    props += [hidden_property(template, k, v) for k, v in sim]

    rest = [c for c in symbol[2:] if not (isinstance(c, list) and c[0] in ("property", "extends"))]
    rest = [c for c in rest if not (isinstance(c, list) and c[0] == "ki_fp_filters")]
    return symbol[:2] + [c for c in rest if isinstance(c, list) and c[0] != "symbol"] + props + \
        [c for c in rest if isinstance(c, list) and c[0] == "symbol"]


def render_library(stock, symbols):
    version, gen_version = stock.header()
    body = ["kicad_symbol_lib", ["version", version], ["generator", quote("openjellybean")],
            ["generator_version", gen_version]] + symbols
    return dump(body) + "\n"


# -------------------------------------------------------------------- main ---
def find_stock_dir(explicit):
    candidates = [explicit, os.environ.get("KICAD_SYMBOL_DIR"), os.environ.get("KICAD9_SYMBOL_DIR"),
                  *STOCK_DIRS]
    for candidate in candidates:
        if candidate and (Path(candidate) / "Device.kicad_sym").is_file():
            return Path(candidate)
    raise SystemExit("KiCad stock symbols not found: pass --kicad-symbols or set KICAD_SYMBOL_DIR")


def generate(stock):
    """Return {library name: file text} for every OpenJellybean library."""
    entries = tomllib.loads(MODELS_TOML.read_text(encoding="utf-8"))
    devices = parse_library(LIBRARY_FILE)
    libraries = {}
    for name, entry in entries.items():
        kind = entry["kind"]
        if kind not in LIBRARY_OF_KIND:
            continue  # kinds with no KiCad symbol here (the potentiometer: KiCad has its own)
        libraries.setdefault(LIBRARY_OF_KIND[kind], []).append(build_symbol(stock, name, entry, devices[name]))
    return {lib: render_library(stock, symbols) for lib, symbols in sorted(libraries.items())}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kicad-symbols", help="directory with the stock KiCad *.kicad_sym files")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    ap.add_argument("--check", action="store_true", help="compare with the files on disk instead of writing")
    args = ap.parse_args(argv)

    texts = generate(Stock(find_stock_dir(args.kicad_symbols)))
    if args.check:
        stale = False
        for lib, text in texts.items():
            path = args.out / f"{lib}.kicad_sym"
            current = path.read_text(encoding="utf-8") if path.is_file() else ""
            if current != text:
                stale = True
                diff = difflib.unified_diff(current.splitlines(), text.splitlines(), str(path), "generated", lineterm="", n=1)
                print("\n".join(list(diff)[:40]))
        print("symbols are stale: run python tools/gen_symbols.py" if stale else "symbols are up to date")
        return 1 if stale else 0
    args.out.mkdir(parents=True, exist_ok=True)
    for lib, text in texts.items():
        (args.out / f"{lib}.kicad_sym").write_text(text, encoding="utf-8")
        print(f"wrote {args.out / (lib + '.kicad_sym')} ({text.count(chr(10) + chr(9) + '(symbol ')} symbols)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
