# Contributing to openjellybean

New models are welcome if they are everyday "jelly bean" parts: common, cheap, and
available from several sources. This guide covers the rules every model must follow
and how to validate one.

## Licensing rules

openjellybean is MIT-licensed, and everything in it must stay that way. By submitting a
contribution, you agree to license it under the [MIT license](LICENSE) and confirm you
have the right to do so.

**Don't use:**

- A manufacturer's SPICE model, even as a starting point: no copying, adapting,
  rescaling or "cleaning up", and no translating to another syntax.
- Models from simulator libraries (LTspice, PSpice, and so on), forums, textbooks or
  other collections, unless the license is explicitly MIT-compatible **and** you keep
  its required notices. If the terms are unclear, treat it as not allowed.
- Anything that came with a EULA, was encrypted, or was marked proprietary or
  confidential.
- Extracted model parameters, such as vendor netlist values copied one by one. Changing
  the format doesn't change where they came from.

**Do:**

- Write the model yourself and fit its parameters to **published datasheet numbers**,
  such as electrical characteristics tables and typical curves.
- Record where those numbers came from in the `source` field of the model's metadata.
- If you used an AI tool or a fitting script, check the result against these same rules.
  You are still responsible for where it came from.

Part numbers are used only to say what a model stands in for. Don't use manufacturer
logos or names in a way that suggests a model is official.

## Modelling rules

- **Use typical values.** A model represents a typical device at 25-27 °C, not a
  worst-case or hand-picked one. If a datasheet only gives limits (common for hFE on
  2N-series parts), land sensibly inside them. Corners are left to the user.
- **Fit what users will notice.** Aim for the characteristics a designer would look up,
  at the conditions the datasheet gives. Don't chase extra digits: `BF=330` is better
  than `BF=331.27`.
- **End names in `_OJ`** so they never collide with vendor models in the same project.
- **Use standard syntax.** Use the standard pin order and only constructs supported by
  both ngspice and LTspice:

  | Type | Form | Pins |
  |---|---|---|
  | BJT | `.model NAME NPN(...)` or `PNP(...)` | C B E |
  | MOSFET | `.model NAME VDMOS(...)`, adding `pchan` for P-channel | D G S |
  | JFET | `.model NAME NJF(...)` or `PJF(...)`, with negative `VTO` for both | D G S |
  | Diode, Schottky, LED | `.model NAME D(...)` | A K |
  | Zener | `.subckt` wrapping `ZENER_OJ`, or `.model NAME D(... BV=...)` | A K |
  | Op-amp | `.subckt` wrapping `OPAMP_OJ`; one amplifier section | +IN -IN V+ V- OUT |
  | Dual op-amp package (`opamp2`) | `.subckt` wrapping two sections | 1OUT 1IN- 1IN+ V- 2IN+ 2IN- 2OUT V+ |
  | Quad op-amp package (`opamp4`) | `.subckt` wrapping four sections | 1OUT 1IN- 1IN+ V+ 2IN+ 2IN- 2OUT 3OUT 3IN- 3IN+ V- 4IN+ 4IN- 4OUT |
  | Potentiometer (`pot`) | `.subckt` with `R` and `POS` parameters | A WIPER B |

- **Comment the model.** Add one line above it saying what it is, and put it in the
  matching section of `jellybean.lib`.
- **State the limits.** If the model leaves out something a user might rely on, add it
  to "Limits" in the README.

## Adding a model

You need [ngspice](https://ngspice.sourceforge.io/) version 47 or later and
Python 3.13 or later. There is nothing to install from pip. If ngspice isn't on your
`PATH`, set the `NGSPICE` environment variable to its location.

**1. Add the model** to `jellybean.lib`.

**2. Describe it** in `tests/models.toml`. This is the metadata the model is tested
against:

```toml
[BC337_OJ]
kind = "npn"                  # npn pnp nmos pmos njfet pjfet diode schottky zener led opamp opamp2 opamp4 pot
stand_in_for = ["BC337-25"]   # the real parts
source = "BC337 datasheet, typical column"
checks = [
  { measure = "hfe", ic = 100e-3, vce = 1, typ = 250 },
  { measure = "hfe", ic = 300e-3, vce = 1, min = 60 },
  { measure = "vcesat", ic = 500e-3, ib = 50e-3, max = 0.7 },
  { measure = "ft", ic = 10e-3, vce = 5, typ = 100e6 },
]
```

Each check names a measure, its test conditions from the datasheet, and an acceptance
band:

| In the check | Passes when the result is within |
|---|---|
| `typ = X` | X ±10 % |
| `typ = X, tol = 0.05` | X ±5 % |
| `min = A`, `max = B`, or both | the datasheet's limits, for when it gives no typical value |

Values are in SI units (`100e-3`, not `100m`). Give PNP and P-channel values as positive
magnitudes, because the test benches apply the polarity for you. Op-amp supplies and
output levels are real node voltages, so `vout_min` can be negative. Op-amp entries can
set `defaults = { vcc = 5, vee = 0 }` to choose the supply for the whole entry.

To see every measure and its conditions, run:

```bash
python tests/validate.py --measures
```

**3. Validate it:**

```bash
python tests/validate.py BC337_OJ
```

This runs three layers of checks, and the command exits non-zero if any of them fail:

1. **Metadata:** the entry is complete and matches the library. For example, the kind
   must match the `.model` type, and the required measures must be present.
2. **Behaviour:** these run automatically for the kind, and catch wrong polarity, swapped
   pins, a device that doesn't turn off, or an op-amp that doesn't settle.
3. **Datasheet targets:** every check in your entry.

**4. Run everything** before opening a pull request:

```bash
python tests/validate.py
```

```bash
python -m unittest discover tests
```

**5. Add a row to the table in `README.md`,** with the target and measured values.

**6. Update the version** in the `jellybean.lib` header:

| Change | Version part to increase |
|---|---|
| Any change to model values | Patch |
| New model in an existing category | Minor |
| Anything larger | Major, at the maintainer's discretion |

### Required measures

An entry must include at least these. Add more wherever the datasheet gives a number,
because each one is another way to catch a bad fit.

| Kind | Required measures | Also available |
|---|---|---|
| `npn`, `pnp` | `hfe`, `vcesat`, `ft` | `vbe`, `vbesat`, `hoe`, `cobo`, `cibo` |
| `nmos`, `pmos` | `vth`, `rdson` | `ciss`, `coss`, `crss`, `vsd` |
| `njfet`, `pjfet` | `idss`, `vgsoff`, `gfs` | `vgs`, `gos`, `rdson`, `ciss`, `crss`, `vgsf`, `igss` |
| `diode`, `schottky` | `vf` | `ir`, `ct`, `trr` |
| `led` | `vf` | `ir`, `ct` |
| `zener` | `vz`, `zz` | `vf`, `ir`, `ct` |
| `opamp` | `aol`, `gbw`, `sr`, `iq`, `vout_max`, `vout_min` | `pm`, `isc`, `vos` |
| `opamp2`, `opamp4` | `iq_total` | `aol`, `gbw`, `pm`, `sr`, `vout_max`, `vout_min` (section 1) |
| `pot` | `rab`, `ratio` | `raw`, `rwb` |

Include `pm` for any op-amp that isn't purely parametric, so that an unstable fit fails.

### Choosing tolerances

Keep the default ±10 % where the model can meet it. If a fit can't, widen `tol` only for
that check, and only as far as it needs, and don't hide a real miss behind a wide band.
Exact-by-construction values (zener `vz`) and logarithmic ones (`vf`, `aol`) should be
much tighter, around 1-3 %.

If a check fails, fix the model rather than the target. Only change the target if the
target itself was wrong.

## Pull request checklist

- [ ] The model is original and fitted to public datasheet values, and no third-party
      model was used.
- [ ] The parameters represent a typical device.
- [ ] The name ends in `_OJ`, and the model is in the right section of `jellybean.lib`.
- [ ] The version in the `jellybean.lib` header is updated.
- [ ] `tests/models.toml` has an entry with a real `source`.
- [ ] `python tests/validate.py` and `python -m unittest discover tests` both pass.
- [ ] The README table is updated, and any new limits are listed.

## Changing the test framework

| File | Purpose |
|---|---|
| `tests/validate.py` | Command line, metadata checks, and reporting |
| `tests/measures.py` | One function per measure, plus the behaviour checks |
| `tests/harness.py` | Runs ngspice and parses the library |
| `tests/smoke.py` | One mixed circuit using every device family |
| `tests/test_framework.py` | Tests that the validator rejects damaged models |
| `tests/models.toml` | The metadata for every model |

To add a measure, write a function in `measures.py` with the `@measure` decorator. Its
keyword arguments become the conditions available in `models.toml`, and `--measures`
lists it automatically. Other device types, such as comparators, need a new
kind and their own benches. Open an issue first to discuss those.

The framework must stay standard-library only.
