"""Standard-library wrapper around ngspice batch mode, plus a .lib parser."""
import math
import os
import re
import shutil
import subprocess
import tempfile
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LIB = ROOT / "jellybean.lib"

# Lines in ngspice's output that mean the result cannot be trusted.
_FAILURE = re.compile(
    r"^.*(\berror\b|simulation\(s\) aborted|no such vector|\bfatal\b|"
    r"could not find|unknown (model|subckt)|timestep too small).*$",
    re.IGNORECASE | re.MULTILINE,
)


class SimError(Exception):
    """ngspice could not be run, reported an error, or returned unusable data."""


def find_ngspice():
    """Return the ngspice executable: $NGSPICE, then PATH, then the Windows default."""
    if env := os.environ.get("NGSPICE"):
        return env
    # On Windows ngspice.exe opens a GUI window; ngspice_con.exe is the console build.
    for name in ("ngspice_con", "ngspice"):
        if found := shutil.which(name):
            return found
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), "C:\\"):
        candidate = Path(base) / "Spice64" / "bin" / "ngspice_con.exe"
        if candidate.exists():
            return str(candidate)
    raise SimError("ngspice not found: put it on PATH or set the NGSPICE environment variable")


class Simulator:
    def __init__(self, lib=DEFAULT_LIB, exe=None):
        self.lib = Path(lib).resolve()
        self.exe = exe or find_ngspice()
        if not shutil.which(self.exe):
            raise SimError(f"ngspice executable not found: {self.exe}")

    def run(self, body, analysis, vectors):
        """Run one analysis and return [scale, vector 0, vector 1, ...] as float lists."""
        script = (
            f'* openjellybean bench\n.include "{self.lib.as_posix()}"\n{body}\n.control\n'
            f"set noaskquit\nset wr_singlescale\n{analysis}\n"
            f"wrdata out.dat {' '.join(vectors)}\nquit\n.endc\n.end\n"
        )
        with tempfile.TemporaryDirectory(prefix="openjellybean-") as tmp:
            (Path(tmp) / "bench.cir").write_text(script)
            try:
                result = subprocess.run(
                    [self.exe, "-b", "bench.cir"],
                    capture_output=True, text=True, errors="replace", cwd=tmp, timeout=300,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise SimError(f"could not run {self.exe}: {exc}") from exc
            output = result.stdout + result.stderr
            if failure := _FAILURE.search(output):
                raise SimError(f"ngspice: {failure[0].strip()}\n--- netlist ---\n{body}")
            try:
                rows = (Path(tmp) / "out.dat").read_text().splitlines()
            except OSError:
                raise SimError(f"ngspice wrote no data\n{output[-1500:]}\n--- netlist ---\n{body}")
        table = [[float(x) for x in row.split()] for row in rows if row.strip()]
        if not table or len(table[0]) != len(vectors) + 1:
            raise SimError(f"unexpected ngspice output for {vectors}\n--- netlist ---\n{body}")
        if any(not math.isfinite(x) for row in table for x in row):
            raise SimError(f"non-finite result for {vectors}\n--- netlist ---\n{body}")
        return [list(column) for column in zip(*table)]

    def op(self, body, *vectors):
        """DC operating point; returns one float per vector."""
        return [column[0] for column in self.run(body, "op", vectors)[1:]]


def interp_log(target, xs, ys):
    """Return y at x == target, interpolating on log(x). xs must rise over the useful range."""
    rising = []
    for x, y in zip(xs, ys):
        if x > 0 and (not rising or x > rising[-1][0]):
            rising.append((x, y))
    keys = [x for x, _ in rising]
    if not keys or not keys[0] <= target <= keys[-1]:
        span = f"{keys[0]:.3g}..{keys[-1]:.3g}" if keys else "empty"
        raise SimError(f"target {target:.3g} is outside the swept range ({span})")
    if len(keys) == 1:
        return rising[0][1]
    k = max(bisect_left(keys, target), 1)
    (x0, y0), (x1, y1) = rising[k - 1], rising[k]
    return y0 + (y1 - y0) * (math.log(target) - math.log(x0)) / (math.log(x1) - math.log(x0))


def crossing(xs, ys, level, rising=True, start=None):
    """Return the first x (at or after start) where y crosses level in the given direction."""
    for k in range(1, len(xs)):
        if start is not None and xs[k] < start:
            continue
        y0, y1 = ys[k - 1], ys[k]
        if (y0 < level <= y1) if rising else (y0 > level >= y1):
            return xs[k - 1] + (xs[k] - xs[k - 1]) * (level - y0) / (y1 - y0)
    raise SimError(f"signal never crossed {level:.3g}")


@dataclass
class Device:
    """A top-level .model or .subckt found in a library file."""
    name: str
    statement: str   # "model" or "subckt"
    type: str = ""   # lower-case .model type (npn, pnp, d, vdmos); empty for a subckt
    pchan: bool = False
    pins: tuple = ()


def parse_library(path):
    """Return {name: Device} for the top-level models and subcircuits of a SPICE library."""
    logical = []
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split(";")[0].strip()
        if line.startswith("+") and logical:
            logical[-1] += " " + line[1:].strip()
        elif line and not line.startswith("*"):
            logical.append(line)

    devices, depth = {}, 0
    for line in logical:
        tokens = line.split()
        keyword = tokens[0].lower()
        if keyword == ".subckt":
            if depth == 0:
                pins = []
                for token in tokens[2:]:
                    if "=" in token or token.lower().rstrip(":") == "params":
                        break
                    pins.append(token.lower())
                devices[tokens[1]] = Device(tokens[1], "subckt", pins=tuple(pins))
            depth += 1
        elif keyword == ".ends":
            depth -= 1
        elif keyword == ".model" and depth == 0:
            model_type = re.match(r"[a-z]+", tokens[2].lower())[0]
            pchan = bool(re.search(r"\bpchan\b", line, re.IGNORECASE))
            devices[tokens[1]] = Device(tokens[1], "model", type=model_type, pchan=pchan)
    return devices
