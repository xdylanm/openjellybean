#!/usr/bin/env python3
"""Validate jellybean.lib against the metadata in tests/models.toml.

    python tests/validate.py                  check everything
    python tests/validate.py BC547B_OJ        check one model (or several)
    python tests/validate.py --measures       list what models.toml can ask for

Exits 0 only if every check passes. Needs ngspice >= 47 and Python >= 3.13, nothing else.
"""
import argparse
import inspect
import re
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from harness import DEFAULT_LIB, SimError, Simulator, parse_library
from measures import BEHAVIOUR, KINDS, MEASURES, PIN_LABELS, Bench, eng
from smoke import run_smoke

DEFAULT_SPEC = Path(__file__).with_name("models.toml")
DEFAULT_TOL = 0.10
RESERVED = {"measure", "typ", "tol", "min", "max"}
ENTRY_KEYS = {"kind", "stand_in_for", "source", "params", "defaults", "checks"}
EXPECTED_MODEL_TYPE = {"npn": "npn", "pnp": "pnp", "nmos": "vdmos", "pmos": "vdmos",
                       "njfet": "njf", "pjfet": "pjf",
                       "diode": "d", "schottky": "d", "zener": "d", "led": "d"}
# Text that suggests vendor-derived content. `mfg=` is the tag vendor libraries carry.
PROVENANCE_FLAGS = re.compile(
    r"all rights reserved|proprietary|confidential|\bmfg\s*=|"
    r"copyright(?!.*openjellybean contributors)|licen[sc]ed (to|under)(?!.*MIT)",
    re.IGNORECASE)


def load_spec(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def band(check):
    """Return the (low, high) acceptance band of a check; either end may be None."""
    if "min" in check or "max" in check:
        return check.get("min"), check.get("max")
    tol = check.get("tol", DEFAULT_TOL)
    a, b = check["typ"] * (1 - tol), check["typ"] * (1 + tol)
    return min(a, b), max(a, b)


def describe_target(check, unit):
    if "min" in check or "max" in check:
        low, high = check.get("min"), check.get("max")
        if low is not None and high is not None:
            return f"{eng(low, unit)} .. {eng(high, unit)}"
        return f">= {eng(low, unit)}" if low is not None else f"<= {eng(high, unit)}"
    return f"{eng(check['typ'], unit)} +-{check.get('tol', DEFAULT_TOL) * 100:g}%"


def lint_library(lib_path):
    """Problems with the library file as a whole."""
    problems = []
    for number, line in enumerate(Path(lib_path).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if PROVENANCE_FLAGS.search(line):
            problems.append(f"{Path(lib_path).name}:{number}: possible third-party content: {line.strip()}")
    return problems


def lint_entry(name, entry, devices):
    """Problems with one models.toml entry and how it matches the library."""
    problems = [f"unknown key '{k}'" for k in entry.keys() - ENTRY_KEYS]
    if not name.endswith("_OJ"):
        problems.append("name must end in _OJ")
    kind = entry.get("kind")
    if kind not in KINDS:
        return problems + [f"kind must be one of {', '.join(KINDS)}, not {kind!r}"]
    if not str(entry.get("source", "")).strip():
        problems.append("'source' must say where the target values come from")
    if not entry.get("stand_in_for") and not entry.get("params"):
        problems.append("'stand_in_for' must name the real parts (only parametric models may omit it)")

    device = devices.get(name)
    if device is None:
        problems.append("not found in the library")
    elif kind in PIN_LABELS:
        expected = PIN_LABELS[kind].split()
        if device.statement != "subckt" or len(device.pins) != len(expected):
            problems.append(f"kind {kind} must be a {len(expected)}-pin .subckt: {PIN_LABELS[kind]}")
    elif device.statement == "subckt":
        if kind != "zener" or len(device.pins) != 2:
            problems.append(f"{kind} must be a .model" + (" or 2-pin .subckt" if kind == "zener" else ""))
    elif device.type != EXPECTED_MODEL_TYPE[kind]:
        problems.append(f"kind {kind} needs a .model of type {EXPECTED_MODEL_TYPE[kind]}, found {device.type}")
    elif kind in ("nmos", "pmos") and device.pchan != (kind == "pmos"):
        problems.append(f"kind {kind} does not match the model's pchan setting")

    checks = entry.get("checks", [])
    named = set()
    for k, check in enumerate(checks, 1):
        measure = MEASURES.get(check.get("measure"))
        if measure is None or kind not in measure.kinds:
            problems.append(f"check {k}: no measure {check.get('measure')!r} for kind {kind}")
            continue
        named.add(measure.name)
        given = check.keys() - RESERVED
        for unknown in given - measure.conditions.keys():
            problems.append(f"check {k} ({measure.name}): unknown condition '{unknown}', "
                            f"expected {', '.join(measure.conditions) or 'none'}")
        for condition, default in measure.conditions.items():
            if default is inspect.Parameter.empty and condition not in given:
                problems.append(f"check {k} ({measure.name}): missing condition '{condition}'")
        if "typ" not in check and "min" not in check and "max" not in check:
            problems.append(f"check {k} ({measure.name}): needs 'typ' or 'min'/'max'")
        for key, value in check.items():
            if key != "measure" and (isinstance(value, bool) or not isinstance(value, (int, float))):
                problems.append(f"check {k} ({measure.name}): '{key}' must be a number in SI units, not {value!r}")
    for measure in MEASURES.values():
        if kind in measure.required and measure.name not in named:
            problems.append(f"missing required measure '{measure.name}' for kind {kind}")
    return problems


def lint_coverage(spec, devices):
    """Every library device must have metadata."""
    return [f"{name}: in the library but has no entry in models.toml"
            for name in devices if name not in spec]


@dataclass
class Result:
    label: str
    passed: bool
    detail: str


def run_check(bench, entry, check):
    measure = MEASURES[check["measure"]]
    conditions = {k: v for k, v in entry.get("defaults", {}).items() if k in measure.conditions}
    conditions |= {k: v for k, v in check.items() if k not in RESERVED}
    shown = " ".join(f"{k}={eng(v)}" for k, v in conditions.items())
    label = f"{measure.name:9s}{shown}"
    try:
        value = measure(bench, **conditions)
    except SimError as exc:
        return Result(label, False, f"could not measure: {exc}")
    low, high = band(check)
    passed = (low is None or value >= low) and (high is None or value <= high)
    return Result(label, passed, f"{eng(value, measure.unit):>10s}   target {describe_target(check, measure.unit)}")


def validate_model(sim, name, entry, devices):
    """Run the automatic behaviour checks and the metadata checks for one model."""
    bench = Bench(sim, devices[name], entry["kind"], entry.get("params", ""))
    results = []
    try:
        for label, passed, detail in BEHAVIOUR[entry["kind"]](bench, **entry.get("defaults", {})):
            results.append(Result(f"behaviour {label}", passed, detail))
    except SimError as exc:
        results.append(Result("behaviour", False, f"could not simulate: {exc}"))
    results += [run_check(bench, entry, check) for check in entry["checks"]]
    return results


def print_measures():
    for kind in KINDS:
        print(f"\n{kind}")
        for m in MEASURES.values():
            if kind not in m.kinds:
                continue
            conditions = ", ".join(
                c if d is inspect.Parameter.empty else f"{c}={d:g}" for c, d in m.conditions.items())
            star = "*" if kind in m.required else " "
            doc = m.func.__doc__.strip()
            print(f"  {star} {m.name:9s} [{m.unit or '-':3s}] ({conditions})  {doc}")
    print("\n* required for every model of that kind. Values and conditions are SI units.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate jellybean.lib against tests/models.toml.")
    parser.add_argument("models", nargs="*", help="model names to check (default: all, plus the smoke test)")
    parser.add_argument("--lib", default=DEFAULT_LIB, help="library file to test")
    parser.add_argument("--spec", default=DEFAULT_SPEC, help="metadata file to test against")
    parser.add_argument("--ngspice", help="ngspice executable (default: $NGSPICE, then PATH)")
    parser.add_argument("--measures", action="store_true", help="list the available measures and exit")
    parser.add_argument("-j", "--jobs", type=int, default=8, help="models to simulate in parallel")
    args = parser.parse_args(argv)
    if args.measures:
        print_measures()
        return 0

    spec = load_spec(args.spec)
    devices = parse_library(args.lib)
    selected = args.models or list(spec)
    unknown = [m for m in selected if m not in spec]
    if unknown:
        print(f"no entry in {Path(args.spec).name} for: {', '.join(unknown)}")
        print("add one first: see CONTRIBUTING.md")
        return 2

    # Structure first: these are instant and make the simulation errors easier to read.
    problems = lint_library(args.lib) + (lint_coverage(spec, devices) if not args.models else [])
    problems += [f"{m}: {p}" for m in selected for p in lint_entry(m, spec[m], devices)]
    if problems:
        print("Metadata problems:")
        for problem in problems:
            print(f"  FAIL {problem}")
        return 1

    try:
        sim = Simulator(args.lib, args.ngspice)
    except SimError as exc:
        print(exc)
        return 2

    failures = total = 0
    with ThreadPoolExecutor(args.jobs) as pool:
        jobs = [pool.submit(validate_model, sim, m, spec[m], devices) for m in selected]
        for name, job in zip(selected, jobs):
            entry = spec[name]
            stands_in = ", ".join(entry.get("stand_in_for", [])) or "parametric"
            print(f"\n{name}  [{entry['kind']}]  {stands_in}")
            for result in job.result():
                total += 1
                failures += not result.passed
                print(f"  {'pass' if result.passed else 'FAIL'}  {result.label:52s} {result.detail}")

    if not args.models:
        print("\nMixed-circuit smoke test")
        try:
            smoke = run_smoke(sim)
        except SimError as exc:
            smoke = [("simulation runs", False, str(exc))]
        for label, passed, detail in smoke:
            total += 1
            failures += not passed
            print(f"  {'pass' if passed else 'FAIL'}  {label:52s} {detail}")

    print(f"\n{total - failures}/{total} checks passed across {len(selected)} model(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    sys.exit(main())
