"""Checks on the KiCad symbol libraries in kicad/symbols.

    python -m unittest discover tests

These need no KiCad install: they parse the committed .kicad_sym files and compare
them with jellybean.lib and tests/models.toml. The check that the files match what
tools/gen_symbols.py would write needs the stock KiCad symbols and is skipped without them.
"""
import sys
import tomllib
import unittest
from pathlib import Path

from harness import DEFAULT_LIB, ROOT, parse_library

sys.path.insert(0, str(ROOT / "tools"))
import gen_symbols as gen  # noqa: E402

SYMBOL_DIR = ROOT / "kicad" / "symbols"
SPEC = tomllib.loads((ROOT / "tests" / "models.toml").read_text(encoding="utf-8"))
DEVICES = parse_library(DEFAULT_LIB)


def load_symbols():
    """{library file stem: {symbol name: symbol node}} for the committed libraries."""
    libraries = {}
    for path in sorted(SYMBOL_DIR.glob("*.kicad_sym")):
        root = gen.parse(path.read_text(encoding="utf-8"))
        libraries[path.stem] = {gen.unquote(s[1]): s for s in gen.children(root, "symbol")}
    return libraries


def fields(symbol):
    return {gen.unquote(p[1]): gen.unquote(p[2]) for p in gen.children(symbol, "property")}


LIBRARIES = load_symbols()
ALL = {name: (lib, sym) for lib, syms in LIBRARIES.items() for name, sym in syms.items()}
EXPECTED = {name: entry for name, entry in SPEC.items() if entry["kind"] in gen.LIBRARY_OF_KIND}


class SymbolLibraries(unittest.TestCase):
    def test_the_four_libraries_exist(self):
        self.assertEqual(sorted(LIBRARIES), sorted(set(gen.LIBRARY_OF_KIND.values())))

    def test_every_model_has_exactly_one_symbol_in_its_library(self):
        self.assertEqual(sorted(ALL), sorted(EXPECTED))
        for name, entry in EXPECTED.items():
            self.assertEqual(ALL[name][0], gen.LIBRARY_OF_KIND[entry["kind"]], name)

    def test_the_potentiometer_has_no_symbol(self):
        self.assertNotIn("POT_OJ", ALL)

    def test_sim_fields_point_at_the_library_model(self):
        for name, (_, symbol) in ALL.items():
            with self.subTest(name):
                props = fields(symbol)
                self.assertEqual(props["Sim.Name"], name)
                self.assertEqual(props["Sim.Library"], gen.SIM_LIBRARY)
                self.assertIn(name, DEVICES)
                expected = "SUBCKT" if DEVICES[name].statement == "subckt" else gen.SIM_DEVICE[EXPECTED[name]["kind"]]
                self.assertEqual(props["Sim.Device"], expected)

    def test_sim_pins_cover_every_symbol_pin_and_follow_the_model_pins(self):
        for name, (_, symbol) in ALL.items():
            with self.subTest(name):
                mapping = dict(pair.split("=") for pair in fields(symbol)["Sim.Pins"].split())
                symbol_pins = {number for number, _ in gen.pins_of(symbol)}
                self.assertEqual(set(mapping), symbol_pins)
                device, kind = DEVICES[name], EXPECTED[name]["kind"]
                if device.statement == "subckt":
                    # every subcircuit pin is wired to exactly one symbol pin
                    self.assertEqual(sorted(mapping.values()), sorted(device.pins))
                    if kind in gen.PACKAGE_KINDS:
                        # pin N of the symbol is node N of the subcircuit, in order
                        self.assertEqual([mapping[str(i + 1)] for i in range(len(device.pins))], list(device.pins))
                else:
                    order = {"npn": "CBE", "pnp": "CBE", "nmos": "DGS", "pmos": "DGS",
                             "njfet": "DGS", "pjfet": "DGS"}.get(kind, "AK")
                    self.assertEqual(sorted(mapping.values()), sorted(order))

    def test_no_footprints_and_a_description(self):
        for name, (_, symbol) in ALL.items():
            with self.subTest(name):
                props = fields(symbol)
                self.assertEqual(props["Footprint"], "")
                self.assertEqual(props["Value"], name)
                self.assertIn("openjellybean", props["Description"])
                self.assertEqual(gen.children(symbol, "extends"), [])  # self-contained
                self.assertNotIn("ki_fp_filters", props)

    def test_symbol_units_are_named_after_the_symbol(self):
        for name, (_, symbol) in ALL.items():
            with self.subTest(name):
                units = [gen.unquote(s[1]) for s in gen.children(symbol, "symbol")]
                self.assertTrue(units)
                self.assertTrue(all(u.startswith(name + "_") for u in units), units)


class Generator(unittest.TestCase):
    def test_committed_files_match_the_generator(self):
        try:
            stock = gen.Stock(gen.find_stock_dir(None))
        except SystemExit:
            self.skipTest("KiCad stock symbols not installed")
        if stock.header()[1] != gen.parse((SYMBOL_DIR / "OpenJellybean_BJT.kicad_sym").read_text())[3][1]:
            self.skipTest("stock KiCad libraries are a different version from the committed output")
        for lib, text in gen.generate(stock).items():
            path = SYMBOL_DIR / f"{lib}.kicad_sym"
            self.assertEqual(path.read_text(encoding="utf-8"), text, f"{path.name} is stale: run tools/gen_symbols.py")

    def test_sexpression_round_trip(self):
        text = '(a "b c" (d 1 2) (e (f "g\\"h")))'
        tree = gen.parse(text)
        self.assertEqual(gen.parse(gen.dump(tree)), tree)
        self.assertEqual(gen.unquote(gen.quote('x"y\\z')), 'x"y\\z')


if __name__ == "__main__":
    unittest.main()
