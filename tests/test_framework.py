"""Tests of the validator itself: does it reject models and metadata it should reject?

    python -m unittest discover tests

Tests that simulate are skipped if ngspice is not installed.
"""
import contextlib
import io
import tempfile
import tomllib
import unittest
from pathlib import Path

from harness import DEFAULT_LIB, SimError, crossing, find_ngspice, interp_log, parse_library
from measures import eng
from validate import DEFAULT_SPEC, band, lint_coverage, lint_entry, lint_library, main

LIBRARY = DEFAULT_LIB.read_text()

try:
    find_ngspice()
    HAVE_NGSPICE = True
except SimError:
    HAVE_NGSPICE = False


def write_temp(test, text, name):
    folder = tempfile.TemporaryDirectory()
    test.addCleanup(folder.cleanup)
    path = Path(folder.name) / name
    path.write_text(text)
    return path


class Helpers(unittest.TestCase):
    def test_interp_log_is_exact_on_a_log_scale(self):
        self.assertAlmostEqual(interp_log(10, [1, 100], [0, 2]), 1)

    def test_interp_log_refuses_to_extrapolate(self):
        with self.assertRaises(SimError):
            interp_log(1000, [1, 100], [0, 2])

    def test_crossing_direction_and_start(self):
        xs, ys = [0, 1, 2, 3], [0, 2, 0, 2]
        self.assertAlmostEqual(crossing(xs, ys, 1), 0.5)
        self.assertAlmostEqual(crossing(xs, ys, 1, rising=False), 1.5)
        self.assertAlmostEqual(crossing(xs, ys, 1, start=2), 2.5)

    def test_band(self):
        self.assertEqual(band({"typ": 100, "tol": 0.5}), (50, 150))
        self.assertEqual(band({"typ": -10, "tol": 0.5}), (-15, -5))
        self.assertEqual(band({"min": 1}), (1, None))

    def test_eng(self):
        self.assertEqual(eng(0.0021, "A"), "2.1 mA")
        self.assertEqual(eng(106, "dB"), "106 dB")


class LibraryParser(unittest.TestCase):
    def test_skips_nested_models_and_reads_pins(self):
        path = write_temp(self, (
            ".model Q_OJ NPN(IS=1e-14\n+ BF=100)\n"
            ".model P_OJ VDMOS(pchan VTO=-2)\n"
            ".subckt Z_OJ a k params: VZ=5\n.model inner D(IS=1n)\n.ends\n"), "x.lib")
        devices = parse_library(path)
        self.assertEqual(set(devices), {"Q_OJ", "P_OJ", "Z_OJ"})
        self.assertEqual(devices["Q_OJ"].type, "npn")
        self.assertTrue(devices["P_OJ"].pchan)
        self.assertEqual(devices["Z_OJ"].pins, ("a", "k"))


class Lint(unittest.TestCase):
    def setUp(self):
        self.devices = parse_library(DEFAULT_LIB)
        self.entry = {
            "kind": "npn", "stand_in_for": ["BC547B"], "source": "datasheet",
            "checks": [{"measure": "hfe", "ic": 2e-3, "typ": 290},
                       {"measure": "vcesat", "ic": 10e-3, "ib": 1e-3, "max": 0.2},
                       {"measure": "ft", "ic": 10e-3, "typ": 300e6}],
        }

    def problems(self):
        return "\n".join(lint_entry("BC547B_OJ", self.entry, self.devices))

    def test_good_entry(self):
        self.assertEqual(self.problems(), "")

    def test_shipped_metadata_is_clean(self):
        spec = tomllib.loads(DEFAULT_SPEC.read_text())
        self.assertEqual(lint_coverage(spec, self.devices), [])
        self.assertEqual(lint_library(DEFAULT_LIB), [])
        for name, entry in spec.items():
            self.assertEqual(lint_entry(name, entry, self.devices), [], name)

    def test_required_measure(self):
        del self.entry["checks"][2]
        self.assertIn("missing required measure 'ft'", self.problems())

    def test_wrong_kind_for_model_type(self):
        self.entry["kind"] = "pnp"
        self.assertIn("needs a .model of type pnp", self.problems())

    def test_unknown_measure(self):
        self.entry["checks"].append({"measure": "vth", "typ": 1})
        self.assertIn("no measure 'vth' for kind npn", self.problems())

    def test_unknown_and_missing_condition(self):
        self.entry["checks"][0] = {"measure": "hfe", "icc": 2e-3, "typ": 290}
        self.assertIn("unknown condition 'icc'", self.problems())
        self.assertIn("missing condition 'ic'", self.problems())

    def test_non_numeric_value(self):
        self.entry["checks"][0]["ic"] = "2m"
        self.assertIn("'ic' must be a number", self.problems())

    def test_check_needs_a_target(self):
        self.entry["checks"][0] = {"measure": "hfe", "ic": 2e-3}
        self.assertIn("needs 'typ' or 'min'/'max'", self.problems())

    def test_source_required(self):
        self.entry["source"] = ""
        self.assertIn("'source'", self.problems())

    def test_library_device_without_metadata(self):
        spec = tomllib.loads(DEFAULT_SPEC.read_text())
        del spec["BS250_OJ"]
        self.assertEqual(len(lint_coverage(spec, self.devices)), 1)

    def test_vendor_text_is_flagged(self):
        for bad in ("* Copyright 2000 Example Semiconductor",
                    "* All rights reserved.",
                    ".model X_OJ D(IS=1n mfg=Example)"):
            path = write_temp(self, bad + "\n", "x.lib")
            self.assertEqual(len(lint_library(path)), 1, bad)


@unittest.skipUnless(HAVE_NGSPICE, "ngspice not installed")
class MutatedModels(unittest.TestCase):
    """Damage one model in a copy of the library; validate.py must then fail on it."""

    def status(self, library, model, spec=None):
        lib = write_temp(self, library, "jellybean.lib")
        args = [model, "--lib", str(lib)] + (["--spec", str(spec)] if spec else [])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(args)
        return code, output.getvalue()

    def damaged(self, old, new):
        self.assertIn(old, LIBRARY)
        return LIBRARY.replace(old, new)

    def assert_fails(self, library, model, measure):
        code, output = self.status(library, model)
        self.assertEqual(code, 1, output)
        failed = [line for line in output.splitlines() if "FAIL" in line]
        self.assertTrue(any(measure in line for line in failed), output)

    def test_undamaged_model_passes(self):
        self.assertEqual(self.status(LIBRARY, "BC547B_OJ")[0], 0)

    def test_low_beta_bjt(self):
        self.assert_fails(self.damaged("NPN(IS=1.8e-14 NF=1 BF=330", "NPN(IS=1.8e-14 NF=1 BF=30"),
                          "BC547B_OJ", "hfe")

    def test_slow_transistor(self):
        self.assert_fails(self.damaged("TF=0.45n", "TF=4.5n"), "BC547B_OJ", "ft")

    def test_wrong_mosfet_threshold(self):
        self.assert_fails(self.damaged("VDMOS(VTO=2.0", "VDMOS(VTO=4.0"), "2N7000_OJ", "vth")

    def test_mosfet_that_does_not_turn_off(self):
        self.assert_fails(self.damaged("VDMOS(VTO=2.0", "VDMOS(VTO=-1.0"), "2N7000_OJ", "off at VGS")

    def test_wrong_diode_drop(self):
        self.assert_fails(self.damaged("D(IS=2.9n N=1.85", "D(IS=2.9u N=1.85"), "1N4148_OJ", "vf")

    def test_slow_diode(self):
        self.assert_fails(self.damaged("TT=2.5n", "TT=25n"), "1N4148_OJ", "trr")

    def test_wrong_zener_voltage(self):
        self.assert_fails(self.damaged("params: VZ=5.1 IZT=5m RZ=40 NK=2", "params: VZ=5.6 IZT=5m RZ=40 NK=2"),
                          "BZX79C5V1_OJ", "vz")

    def test_opamp_with_swapped_inputs(self):
        self.assert_fails(self.damaged(".subckt TL07X_OJ inp inn vcc vee out\n", ".subckt TL07X_OJ inn inp vcc vee out\n"),
                          "TL07X_OJ", "pin order")

    def test_unstable_opamp(self):
        self.assert_fails(self.damaged("ROUT=100 FP2=4.5e6\n.ends TL07X_OJ", "ROUT=100 FP2=4.5e3\n.ends TL07X_OJ"),
                          "TL07X_OJ", "pm")

    def test_opamp_with_broken_netlist_reports_a_failure(self):
        self.assert_fails(self.damaged("Rint int mid {AOL/GM}", "Rint int mid {NOPE}"), "TL07X_OJ", "could not")

    def test_new_model_end_to_end(self):
        """The CONTRIBUTING.md workflow: add a .model and an entry, then validate just that."""
        library = LIBRARY + "\n.model TEST_OJ D(IS=2.9n N=1.85 RS=0.9 BV=100 IBV=100u CJO=2p TT=2.5n)\n"
        entry = '[TEST_OJ]\nkind = "diode"\nstand_in_for = ["TEST"]\nsource = "unit test"\n' \
                'checks = [ { measure = "vf", i = 1e-3, typ = 0.61, tol = 0.03 } ]\n'
        spec = write_temp(self, DEFAULT_SPEC.read_text() + "\n" + entry, "models.toml")
        code, output = self.status(library, "TEST_OJ", spec)
        self.assertEqual(code, 0, output)
        self.assertIn("vf", output)


if __name__ == "__main__":
    unittest.main()
