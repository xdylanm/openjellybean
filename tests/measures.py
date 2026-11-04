"""Benches: one function per datasheet quantity, plus automatic behaviour checks.

Every @measure function takes a Bench and keyword-only conditions in SI units, and
returns a value in SI units. A condition with no default must be given in models.toml;
`python tests/validate.py --measures` prints this registry.

Currents and voltages are magnitudes: benches apply the polarity for PNP and P-channel
parts, so models.toml describes them with positive numbers. Op-amp output levels and
supplies are the exception, because there they are real node voltages.
"""
import inspect
import math
from dataclasses import dataclass

from harness import crossing, interp_log

BJT = ("npn", "pnp")
MOSFET = ("nmos", "pmos")
DIODE = ("diode", "schottky", "zener", "led")
OPAMP = ("opamp",)
PACKAGE = ("opamp2", "opamp4")
POT = ("pot",)
KINDS = BJT + MOSFET + DIODE + OPAMP + PACKAGE + POT

# Package pins in pin-number order. Benches wire by position, so a library .subckt
# with its pins in the wrong order fails however it names them.
PACKAGE_PINS = {
    "opamp2": ("out1", "inn1", "inp1", "vee", "inp2", "inn2", "out2", "vcc"),
    "opamp4": ("out1", "inn1", "inp1", "vcc", "inp2", "inn2", "out2",
               "out3", "inn3", "inp3", "vee", "inp4", "inn4", "out4"),
}
PIN_LABELS = {
    "opamp": "+IN -IN V+ V- OUT",
    "opamp2": "1OUT 1IN- 1IN+ V- 2IN+ 2IN- 2OUT V+",
    "opamp4": "1OUT 1IN- 1IN+ V+ 2IN+ 2IN- 2OUT 3OUT 3IN- 3IN+ V- 4IN+ 4IN- 4OUT",
    "pot": "A WIPER B",
}

_PREFIX = {"npn": "Q", "pnp": "Q", "nmos": "M", "pmos": "M",
           "diode": "D", "schottky": "D", "zener": "D", "led": "D", "opamp": "X"}
TWO_PI = 2 * math.pi


class Bench:
    """One device under test on one simulator."""

    def __init__(self, sim, device, kind, params=""):
        self.sim = sim
        self.device = device
        self.kind = kind
        self.params = params
        self.sign = -1 if kind in ("pnp", "pmos") else 1

    def part(self, *nodes):
        """Instance line for the device under test, wired to nodes in SPICE pin order."""
        if self.kind in PACKAGE and len(nodes) == 5:
            return self._first_section(*nodes)
        prefix = "X" if self.device.statement == "subckt" else _PREFIX[self.kind]
        suffix = f" params: {self.params}" if self.params else ""
        return f"{prefix}1 {' '.join(nodes)} {self.device.name}{suffix}"

    def _first_section(self, inp, inn, vcc, vee, out):
        """Package with section 1 on the given nodes and the rest as idle followers."""
        nodes = {"vcc": vcc, "vee": vee, "inp1": inp, "inn1": inn, "out1": out}
        for k in range(2, _sections(self.kind) + 1):
            nodes |= {f"inp{k}": "idle", f"inn{k}": f"idle_out{k}", f"out{k}": f"idle_out{k}"}
        wiring = (nodes[pin] for pin in PACKAGE_PINS[self.kind])
        return f"Ri1 {vcc} idle 1Meg\nRi2 idle {vee} 1Meg\n" + self.part(*wiring)


@dataclass
class Measure:
    name: str
    func: object
    kinds: tuple
    unit: str
    required: tuple  # kinds that must specify this measure
    conditions: dict  # name -> default, or inspect.Parameter.empty when mandatory

    def __call__(self, bench, **conditions):
        return self.func(bench, **conditions)


MEASURES = {}


def measure(kinds, unit, required=False):
    """Register a bench. required (True, or a subset of kinds) makes those models specify it."""
    def register(func):
        signature = inspect.signature(func).parameters.values()
        conditions = {p.name: p.default for p in signature if p.kind == p.KEYWORD_ONLY}
        needed_by = kinds if required is True else required or ()
        MEASURES[func.__name__] = Measure(func.__name__, func, kinds, unit, needed_by, conditions)
        return func
    return register


# ------------------------------------------------------------------- BJTs ---
def _gummel(b, vce):
    """Sweep VBE at fixed VCE; return (vbe, ic, ib) as magnitudes."""
    s = b.sign
    vbe, ic, ib = b.sim.run(
        f"VC c 0 {s * vce}\nVB b 0 0\n{b.part('c', 'b', '0')}",
        f"dc VB 0 {s * 1.5} {s * 1e-3}", ["abs(i(VC))", "abs(i(VB))"])
    return [abs(v) for v in vbe], ic, ib


def _ib_for(b, ic, vce):
    _, ics, ibs = _gummel(b, vce)
    return interp_log(ic, ics, ibs)


@measure(BJT, "", required=True)
def hfe(b, *, ic, vce=5.0):
    """DC current gain IC/IB."""
    return ic / _ib_for(b, ic, vce)


@measure(BJT, "V")
def vbe(b, *, ic, vce=5.0):
    """Base-emitter voltage in the active region."""
    vbes, ics, _ = _gummel(b, vce)
    return interp_log(ic, ics, vbes)


def _saturated(b, ic, ib, node):
    s = b.sign
    return b.sim.op(f"IC 0 c {s * ic}\nIB 0 b {s * ib}\n{b.part('c', 'b', '0')}",
                    f"abs(v({node}))")[0]


@measure(BJT, "V", required=True)
def vcesat(b, *, ic, ib):
    """Collector-emitter saturation voltage at forced IC, IB."""
    return _saturated(b, ic, ib, "c")


@measure(BJT, "V")
def vbesat(b, *, ic, ib):
    """Base-emitter voltage in saturation at forced IC, IB."""
    return _saturated(b, ic, ib, "b")


@measure(BJT, "S")
def hoe(b, *, ic, vce=5.0, dv=1.0):
    """Output conductance dIC/dVCE at constant IB (Early voltage is about IC/hoe)."""
    s = b.sign
    ib = _ib_for(b, ic, vce)
    _, ics = b.sim.run(f"VC c 0 {s * vce}\nIB 0 b {s * ib}\n{b.part('c', 'b', '0')}",
                       f"dc VC {s * (vce - dv / 2)} {s * (vce + dv / 2)} {s * dv}", ["abs(i(VC))"])
    return (ics[-1] - ics[0]) / dv


@measure(BJT, "Hz", required=True)
def ft(b, *, ic, vce=5.0, f=20e6):
    """Transition frequency: |h21| * f. Pick f on the -20 dB/decade slope, below fT."""
    s = b.sign
    ib = _ib_for(b, ic, vce)
    _, h21 = b.sim.run(f"VC c 0 {s * vce}\nIB 0 b dc {s * ib} ac 1\n{b.part('c', 'b', '0')}",
                       f"ac lin 1 {f} {f}", ["mag(i(VC))"])
    return h21[0] * f


@measure(BJT, "F")
def cobo(b, *, vcb=5.0, f=1e6):
    """Output capacitance, emitter open."""
    _, i = b.sim.run(f"VC c 0 dc {b.sign * vcb} ac 1\nVB b 0 0\n{b.part('c', 'b', 'e')}\nRe e 0 1e12",
                     f"ac lin 1 {f} {f}", ["mag(i(VC))"])
    return i[0] / (TWO_PI * f)


@measure(BJT, "F")
def cibo(b, *, veb=0.5, f=1e6):
    """Input capacitance, collector open."""
    _, i = b.sim.run(f"VE e 0 dc {b.sign * veb} ac 1\nVB b 0 0\n{b.part('c', 'b', 'e')}\nRc c 0 1e12",
                     f"ac lin 1 {f} {f}", ["mag(i(VE))"])
    return i[0] / (TWO_PI * f)


# --------------------------------------------------------------- MOSFETs ----
@measure(MOSFET, "V", required=True)
def vth(b, *, id=1e-3, vds=5.0):
    """Gate threshold |VGS| at a given drain current."""
    s = b.sign
    vgs, ids = b.sim.run(f"VD d 0 {s * vds}\nVG g 0 0\n{b.part('d', 'g', '0')}",
                         f"dc VG 0 {s * 10} {s * 2e-3}", ["abs(i(VD))"])
    return interp_log(id, ids, [abs(v) for v in vgs])


@measure(MOSFET, "ohm", required=True)
def rdson(b, *, vgs, id):
    """On resistance at a given gate drive and drain current."""
    s = b.sign
    v = b.sim.op(f"VG g 0 {s * vgs}\nID 0 d {s * id}\n{b.part('d', 'g', '0')}", "abs(v(d))")[0]
    return v / id


def _gate_ac(b, vds, f, source):
    s = b.sign
    _, i = b.sim.run(f"VD d 0 dc {s * vds} ac 0\nVG g 0 dc 0 ac 1\n{b.part('d', 'g', '0')}",
                     f"ac lin 1 {f} {f}", [f"mag(i({source}))"])
    return i[0] / (TWO_PI * f)


@measure(MOSFET, "F")
def ciss(b, *, vds=25.0, f=1e6):
    """Input capacitance at VGS = 0."""
    return _gate_ac(b, vds, f, "VG")


@measure(MOSFET, "F")
def crss(b, *, vds=25.0, f=1e6):
    """Reverse transfer capacitance at VGS = 0."""
    return _gate_ac(b, vds, f, "VD")


@measure(MOSFET, "F")
def coss(b, *, vds=25.0, f=1e6):
    """Output capacitance at VGS = 0."""
    _, i = b.sim.run(f"VD d 0 dc {b.sign * vds} ac 1\nVG g 0 0\n{b.part('d', 'g', '0')}",
                     f"ac lin 1 {f} {f}", ["mag(i(VD))"])
    return i[0] / (TWO_PI * f)


@measure(MOSFET, "V")
def vsd(b, *, i):
    """Body diode forward voltage."""
    return b.sim.op(f"IS 0 s {b.sign * i}\nVG g 0 0\n{b.part('0', 'g', 's')}", "abs(v(s))")[0]


# ---------------------------------------------------------------- Diodes ----
@measure(DIODE, "V", required=("diode", "schottky", "led"))
def vf(b, *, i):
    """Forward voltage."""
    return b.sim.op(f"I1 0 a {i}\n{b.part('a', '0')}", "v(a)")[0]


@measure(DIODE, "A")
def ir(b, *, vr):
    """Reverse leakage at a voltage below breakdown."""
    return b.sim.op(f"V1 k 0 {vr}\n{b.part('0', 'k')}", "abs(i(V1))")[0]


@measure(DIODE, "F")
def ct(b, *, vr, f=1e6):
    """Total capacitance at a reverse voltage."""
    _, i = b.sim.run(f"V1 k 0 dc {vr} ac 1\n{b.part('0', 'k')}", f"ac lin 1 {f} {f}", ["mag(i(V1))"])
    return i[0] / (TWO_PI * f)


@measure(("diode", "schottky"), "s")
def trr(b, *, i_f=10e-3, i_r=10e-3, i_stop=1e-3, r=1e3, t_flip=100e-9, t_rec=30e-9):
    """Reverse recovery, reversal to i_stop. Slow rectifiers need larger t_flip and t_rec."""
    t_end = t_flip + t_rec
    step = t_end / 20000  # trr is step-sensitive: 50 ps reads about 2 % high on a 4 ns part
    # i(V1) is negative while the diode conducts forward, positive during recovery.
    t, i = b.sim.run(
        f"V1 s 0 PULSE({i_f * r + 0.7} {-i_r * r} {t_flip} 0.1n 0.1n {2 * t_end} {4 * t_end})\nR1 s a {r}\n{b.part('a', '0')}",
        f"tran {step} {t_end} 0 {step}", ["i(V1)"])
    t_zero = crossing(t, i, 0.0, rising=True, start=t_flip)
    return crossing(t, i, i_stop, rising=False, start=t_zero) - t_zero


# ---------------------------------------------------------------- Zeners ----
def _reverse_v(b, i):
    return b.sim.op(f"I1 0 k {i}\n{b.part('0', 'k')}", "v(k)")[0]


@measure(("zener",), "V", required=True)
def vz(b, *, i):
    """Zener voltage at a given reverse current."""
    return _reverse_v(b, i)


@measure(("zener",), "ohm", required=True)
def zz(b, *, i):
    """Dynamic impedance at a given reverse current (+/-10 % finite difference)."""
    return (_reverse_v(b, 1.1 * i) - _reverse_v(b, 0.9 * i)) / (0.2 * i)


# --------------------------------------------------------------- Op-amps ----
def _supplies(vcc, vee):
    return f"VP vcc 0 {vcc}\nVN vee 0 {vee}\n"


def _open_loop(b, vcc, vee, rl):
    """AC-drive -IN with DC feedback through a huge inductor; return (f, dB, phase in deg)."""
    mid = (vcc + vee) / 2
    body = (_supplies(vcc, vee) + f"VI inp 0 {mid}\n{b.part('inp', 'inn', 'vcc', 'vee', 'out')}\n"
            f"Rf out fb 1k\nLb fb inn 1T\nCb inn ac 1\nVA ac 0 dc 0 ac 1\nRL out 0 {rl}")
    f, db, rad = b.sim.run(body, "ac dec 50 0.1 1e9", ["vdb(out)", "vp(out)"])
    degrees = [rad[0]]
    for r in rad[1:]:
        degrees.append(r + TWO_PI * round((degrees[-1] - r) / TWO_PI))
    return f, db, [math.degrees(r) for r in degrees]


@measure(OPAMP + PACKAGE, "dB", required=OPAMP)
def aol(b, *, vcc=15.0, vee=-15.0, rl=10e3):
    """Open-loop DC gain."""
    return _open_loop(b, vcc, vee, rl)[1][0]


@measure(OPAMP + PACKAGE, "Hz", required=OPAMP)
def gbw(b, *, vcc=15.0, vee=-15.0, rl=10e3):
    """Unity-gain frequency of the open-loop response."""
    f, db, _ = _open_loop(b, vcc, vee, rl)
    return crossing(f, db, 0.0, rising=False)


@measure(OPAMP + PACKAGE, "deg")
def pm(b, *, vcc=15.0, vee=-15.0, rl=10e3):
    """Phase margin at the unity-gain frequency."""
    f, db, phase = _open_loop(b, vcc, vee, rl)
    fu = crossing(f, db, 0.0, rising=False)
    lag = phase[0] - interp_log(fu, f, phase)
    return 180 - lag


@measure(OPAMP + PACKAGE, "V/s", required=OPAMP)
def sr(b, *, vcc=15.0, vee=-15.0, rl=10e3, t_settle=500e-6):
    """Rising slew rate of a unity follower, 20-80 % of the step (t_settle must span the edge)."""
    mid = (vcc + vee) / 2
    step = min(10.0, (vcc - vee) / 3)
    t, v = b.sim.run(
        _supplies(vcc, vee)
        + f"VI inp 0 PULSE({mid - step / 2} {mid + step / 2} 1u 1n 1n {2 * t_settle} {4 * t_settle})\n"
        + f"{b.part('inp', 'out', 'vcc', 'vee', 'out')}\nRL out 0 {rl}",
        f"tran 10n {t_settle} 0 50n", ["v(out)"])
    t1 = crossing(t, v, mid - 0.3 * step, start=1e-6)
    t2 = crossing(t, v, mid + 0.3 * step, start=t1)
    return 0.6 * step / (t2 - t1)


def _saturate(b, vcc, vee, rl, high):
    mid = (vcc + vee) / 2
    overdrive = 1 if high else -1
    return b.sim.op(_supplies(vcc, vee) + f"VI inp 0 {mid}\nVD inn 0 {mid - overdrive}\n"
                    f"{b.part('inp', 'inn', 'vcc', 'vee', 'out')}\nRL out 0 {rl}", "v(out)")[0]


@measure(OPAMP + PACKAGE, "V", required=OPAMP)
def vout_max(b, *, vcc=15.0, vee=-15.0, rl=10e3):
    """Highest output voltage (load returned to ground)."""
    return _saturate(b, vcc, vee, rl, high=True)


@measure(OPAMP + PACKAGE, "V", required=OPAMP)
def vout_min(b, *, vcc=15.0, vee=-15.0, rl=10e3):
    """Lowest output voltage (load returned to ground)."""
    return _saturate(b, vcc, vee, rl, high=False)


@measure(OPAMP, "A", required=True)
def iq(b, *, vcc=15.0, vee=-15.0):
    """Supply current of one amplifier, unloaded follower at mid-supply."""
    mid = (vcc + vee) / 2
    return b.sim.op(_supplies(vcc, vee) + f"VI inp 0 {mid}\n{b.part('inp', 'out', 'vcc', 'vee', 'out')}",
                    "abs(i(VP))")[0]


@measure(OPAMP, "A")
def isc(b, *, vcc=15.0, vee=-15.0):
    """Sourcing short-circuit current, output shorted to ground."""
    mid = (vcc + vee) / 2
    return b.sim.op(_supplies(vcc, vee) + f"VI inp 0 {mid + 1}\nVD inn 0 {mid}\nVS out 0 0\n"
                    f"{b.part('inp', 'inn', 'vcc', 'vee', 'out')}", "abs(i(VS))")[0]


@measure(OPAMP, "V")
def vos(b, *, vcc=15.0, vee=-15.0):
    """Input offset magnitude, from a follower at mid-supply."""
    mid = (vcc + vee) / 2
    out = b.sim.op(_supplies(vcc, vee) + f"VI inp 0 {mid}\n{b.part('inp', 'out', 'vcc', 'vee', 'out')}",
                   "v(out)")[0]
    return abs(out - mid)


# --------------------------------------------------------- Op-amp packages ---
def _sections(kind):
    return {"opamp2": 2, "opamp4": 4}[kind]


def _package(b, vcc, vee, **overrides):
    """Instance line with each section an idle follower at ref, except for overrides."""
    nodes = {"vcc": "vcc", "vee": "vee"}
    for k in range(1, _sections(b.kind) + 1):
        nodes |= {f"inp{k}": "ref", f"inn{k}": f"out{k}", f"out{k}": f"out{k}"}
    nodes |= overrides
    mid = (vcc + vee) / 2
    return _supplies(vcc, vee) + f"VM ref 0 {mid}\n" + b.part(*(nodes[pin] for pin in PACKAGE_PINS[b.kind]))


@measure(PACKAGE, "A", required=True)
def iq_total(b, *, vcc=15.0, vee=-15.0):
    """Supply current of the whole package, unloaded followers at mid-supply."""
    return b.sim.op(_package(b, vcc, vee), "abs(i(VP))")[0]


# ----------------------------------------------------------- Potentiometers ---
def _resistance(b, *nodes):
    return b.sim.op(f"I1 0 a 1m\n{b.part(*nodes)}", "v(a)")[0] / 1e-3


@measure(POT, "ohm", required=True)
def rab(b):
    """Total resistance from A to B."""
    return _resistance(b, "a", "w", "0")


@measure(POT, "ohm")
def raw(b):
    """Resistance from A to the wiper."""
    return _resistance(b, "a", "0", "b")


@measure(POT, "ohm")
def rwb(b):
    """Resistance from the wiper to B."""
    return _resistance(b, "x", "a", "0")


@measure(POT, "", required=True)
def ratio(b):
    """Wiper voltage as a fraction of the voltage from A to B, with B grounded."""
    return b.sim.op(f"V1 a 0 1\n{b.part('a', 'w', '0')}", "v(w)")[0]


# ---------------------------------------------- Automatic behaviour checks ---
# These need no metadata beyond the kind, and catch the errors a datasheet table can
# miss: swapped pins, wrong polarity, a device that never turns off. Each returns
# (description, passed, detail).
def _behaviour_bjt(b, **_):
    s = b.sign
    def ic(vbe_drive):
        return b.sim.op(f"VC c 0 {s * 5}\nVB b 0 {vbe_drive}\n{b.part('c', 'b', '0')}", "abs(i(VC))")[0]
    # Collector current must flow into an NPN collector, i.e. out of the VC source's + pin.
    on_signed = b.sim.op(f"VC c 0 {s * 5}\nVB b 0 {s * 0.7}\n{b.part('c', 'b', '0')}", "i(VC)")[0]
    on, off, wrong = ic(s * 0.7), ic(0), ic(-s * 0.7)
    return [
        ("conducts with forward VBE", on > 1e-6 and on_signed * s < 0, f"IC={eng(on, 'A')} at VBE=0.7 V"),
        ("off at VBE = 0", off < 1e-6, f"IC={eng(off, 'A')}"),
        ("off with reversed VBE (polarity)", wrong < 1e-6, f"IC={eng(wrong, 'A')}"),
    ]


def _behaviour_mosfet(b, **_):
    s = b.sign
    def idrain(vgs):
        return b.sim.op(f"VD d 0 {s * 5}\nVG g 0 {vgs}\n{b.part('d', 'g', '0')}", "abs(i(VD))")[0]
    on, off, wrong = idrain(s * 10), idrain(0), idrain(-s * 10)
    body = b.sim.op(f"VD d 0 {-s * 1}\nVG g 0 0\n{b.part('d', 'g', '0')}", "abs(i(VD))")[0]
    return [
        ("conducts with VGS = 10 V", on > 1e-3, f"ID={eng(on, 'A')}"),
        ("off at VGS = 0", off < 10e-6, f"ID={eng(off, 'A')}"),
        ("off with reversed VGS (polarity)", wrong < 10e-6, f"ID={eng(wrong, 'A')}"),
        ("body diode conducts", body > 1e-3, f"I={eng(body, 'A')} at VSD=1 V"),
    ]


def _behaviour_diode(b, **_):
    forward = b.sim.op(f"I1 0 a 10m\n{b.part('a', '0')}", "v(a)")[0]
    reverse = b.sim.op(f"V1 k 0 1\n{b.part('0', 'k')}", "abs(i(V1))")[0]
    checks = [
        ("forward drop plausible at 10 mA", 0.1 < forward < 1.3, f"VF={eng(forward, 'V')}"),
        ("blocks at 1 V reverse", reverse < 100e-6, f"IR={eng(reverse, 'A')}"),
    ]
    if b.kind == "schottky":
        checks.append(("forward drop below silicon", forward < 0.55, f"VF={eng(forward, 'V')}"))
    if b.kind == "zener":
        low, high = _reverse_v(b, 1e-3), _reverse_v(b, 10e-3)
        checks.append(("reverse breakdown rises with current", 1.0 < low < high,
                       f"{eng(low, 'V')} at 1 mA, {eng(high, 'V')} at 10 mA"))
    return checks


def _behaviour_led(b, **_):
    forward = b.sim.op(f"I1 0 a 10m\n{b.part('a', '0')}", "v(a)")[0]
    dim = b.sim.op(f"V1 a 0 1\n{b.part('a', '0')}", "abs(i(V1))")[0]
    reverse = b.sim.op(f"V1 k 0 5\n{b.part('0', 'k')}", "abs(i(V1))")[0]
    return [
        ("forward drop plausible at 10 mA", 1.4 < forward < 3.6, f"VF={eng(forward, 'V')}"),
        ("stays off at 1 V forward", dim < 10e-6, f"IF={eng(dim, 'A')}"),
        ("blocks at 5 V reverse", reverse < 100e-6, f"IR={eng(reverse, 'A')}"),
    ]


def _behaviour_opamp(b, *, vcc=15.0, vee=-15.0, **_):
    mid = (vcc + vee) / 2
    sup = _supplies(vcc, vee)
    d = min(1.0, (vcc - vee) / 10)  # leaves headroom on a low supply
    follower = b.sim.op(sup + f"VI inp 0 {mid + d}\n{b.part('inp', 'out', 'vcc', 'vee', 'out')}", "v(out)")[0]
    # .op can settle on the unstable solution of a feedback loop, so test the input
    # polarity open loop: this is what catches swapped pins.
    high = _saturate(b, vcc, vee, 10e3, high=True)
    low = _saturate(b, vcc, vee, 10e3, high=False)
    inverting = b.sim.op(
        sup + f"VM ref 0 {mid}\nVI in 0 {mid + d / 2}\nR1 in inn 10k\nR2 inn out 20k\n"
        f"{b.part('ref', 'inn', 'vcc', 'vee', 'out')}", "v(out)")[0]
    # A step must settle at the target instead of ringing or oscillating.
    t, v = b.sim.run(
        sup + f"VI inp 0 PULSE({mid} {mid + 0.1} 1u 1n 1n 1 2)\n{b.part('inp', 'out', 'vcc', 'vee', 'out')}\n"
        f"RL out 0 10k", "tran 10n 200u 0 100n", ["v(out)"])
    tail = v[len(v) * 3 // 4:]
    ripple = max(tail) - min(tail)
    return [
        ("unity follower tracks +IN", abs(follower - (mid + d)) < 0.05, f"out-mid={eng(follower - mid, 'V')} for {eng(d, 'V')} in"),
        ("output follows +IN minus -IN (pin order)", low < mid < high, f"{eng(low, 'V')} .. {eng(high, 'V')}"),
        ("inverting amp has gain -2", abs((inverting - mid) + d) < 0.05, f"out-mid={eng(inverting - mid, 'V')}"),
        ("follower settles after a step", ripple < 1e-3, f"ripple={eng(ripple, 'V')}"),
    ]


def _behaviour_package(b, *, vcc=15.0, vee=-15.0, **_):
    mid = (vcc + vee) / 2
    d = min(1.0, (vcc - vee) / 10)
    checks = []
    outs = [f"out{k}" for k in range(1, _sections(b.kind) + 1)]
    for k, out in enumerate(outs, 1):
        # Only this section may respond: a wiring mistake moves the wrong output.
        body = _package(b, vcc, vee, **{f"inp{k}": "in"}) + f"\nVI in 0 {mid + d}"
        values = dict(zip(outs, b.sim.op(body, *(f"v({o})" for o in outs))))
        others = max((abs(v - mid) for o, v in values.items() if o != out), default=0.0)
        checks.append((f"section {k} follows its +IN, others stay idle",
                       abs(values[out] - (mid + d)) < 0.05 and others < 0.05,
                       f"out-mid={eng(values[out] - mid, 'V')}, others within {eng(others, 'V')}"))
        def drive(level):
            return b.sim.op(_package(b, vcc, vee, **{f"inp{k}": "in", f"inn{k}": "ref"})
                            + f"\nVI in 0 {mid + level}", f"v({out})")[0]
        high, low = drive(d), drive(-d)
        checks.append((f"section {k} output follows +IN minus -IN (pin order)", low < mid < high,
                       f"{eng(low, 'V')} .. {eng(high, 'V')}"))
    return checks


def _behaviour_pot(b, **_):
    def at(pos):
        return ratio(Bench(b.sim, b.device, b.kind, f"POS={pos}"))
    start, middle, end, past = at(0), at(0.5), at(1), at(2)
    return [
        ("wiper reaches A at POS = 0", abs(start - 1) < 1e-3, f"ratio={start:.4f}"),
        ("wiper is centred at POS = 0.5", abs(middle - 0.5) < 1e-3, f"ratio={middle:.4f}"),
        ("wiper reaches B at POS = 1", abs(end) < 1e-3, f"ratio={end:.4f}"),
        ("POS is limited to 0..1", abs(past - end) < 1e-6, f"ratio={past:.4f} at POS = 2"),
    ]


BEHAVIOUR = {"npn": _behaviour_bjt, "pnp": _behaviour_bjt,
             "nmos": _behaviour_mosfet, "pmos": _behaviour_mosfet,
             "diode": _behaviour_diode, "schottky": _behaviour_diode, "zener": _behaviour_diode,
             "opamp": _behaviour_opamp,
             "led": _behaviour_led, "opamp2": _behaviour_package, "opamp4": _behaviour_package, "pot": _behaviour_pot}


def eng(value, unit=""):
    """Format with an SI prefix: eng(0.0021, 'A') -> '2.1 mA'."""
    if value == 0 or not math.isfinite(value) or unit in ("dB", "deg"):
        return f"{value:.4g} {unit}".strip()
    exponent = max(min(math.floor(math.log10(abs(value)) / 3) * 3, 12), -15)
    prefix = {-15: "f", -12: "p", -9: "n", -6: "u", -3: "m", 0: "", 3: "k", 6: "M", 9: "G", 12: "T"}[exponent]
    return f"{value / 10 ** exponent:.4g} {prefix}{unit}".strip()
