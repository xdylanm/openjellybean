# openjellybean — MIT-licensed jelly-bean SPICE models

One include file, `jellybean.lib`, with original models that behave like the
everyday parts. Every model was written from scratch and its parameters fitted
in ngspice to **typical** values from public datasheets — no manufacturer model
file was copied or adapted — so the whole set is under the MIT license.

Names end in `_OJ` so they never collide with vendor models.

```spice
.include jellybean.lib
Q1  c b e  BC547B_OJ          ; BJT:      C B E  (SPICE order, not TO-92 pin order)
M1  d g s  2N7000_OJ          ; VDMOS:    D G S  (body diode built in)
D1  a k    1N4148_OJ          ; diode:    A K
X1  a k    BZX79C5V1_OJ       ; zener:    A K
X2  a k    ZENER_OJ params: VZ=8.2 IZT=5m RZ=10 NK=1   ; any voltage
XU1 inp inn vcc vee out TL07X_OJ   ; op-amp: +IN -IN V+ V- OUT
```

## Contents and verified behaviour (ngspice 47, 27 °C)

| Model | Stand-in for | Target (datasheet typ.) | Model |
|---|---|---|---|
| `BC547B_OJ` NPN | BC547B | hFE 290 @ 2 mA; 150 @ 10 µA | 282; 162 |
| | | VBE 0.66 V @ 2 mA | 0.658 V |
| | | VCE(sat) 90 / 200 mV @ 10 / 100 mA | 69 / 231 mV |
| | | hoe 30 µS @ 2 mA (VA ≈ 65 V) | 30 µS |
| | | fT 300 MHz @ 10 mA | 304 MHz |
| `BC557B_OJ` PNP | BC557B | hFE 290 @ 2 mA | 289 |
| | | VCE(sat) 75 / 250 mV @ 10 / 100 mA | 64 / 247 mV |
| | | fT 150 MHz | 150 MHz |
| `2N3904_OJ` NPN | 2N3904, MMBT3904 | hFE 100–300 @ 10 mA (min 70 @ 1 mA, 30 @ 100 mA), VCE = 1 V | 157 (164 @ 1 mA, 75 @ 100 mA) |
| | | VCE(sat) ≤ 200 / 300 mV @ 10/1, 50/5 mA | 54 / 119 mV |
| | | fT ≥ 300 MHz (20 V, 10 mA, 100 MHz); Cobo ≤ 4 pF; Cibo ≤ 8 pF | 361 MHz; 2.4 pF; 5.0 pF |
| `2N3906_OJ` PNP | 2N3906, MMBT3906 | hFE 100–300 @ 10 mA (min 30 @ 100 mA), VCE = 1 V | 158 (79 @ 100 mA) |
| | | VCE(sat) ≤ 250 / 400 mV @ 10/1, 50/5 mA | 61 / 150 mV |
| | | fT ≥ 250 MHz (20 V, 10 mA, 100 MHz); Cobo ≤ 4.5 pF; Cibo ≤ 10 pF | 289 MHz; 3.1 pF; 6.7 pF |
| `2N7000_OJ` NMOS | 2N7000, 2N7002, BS170 | VGS(th) 2.1 V @ 1 mA | 2.02 V |
| | | RDS(on) 1.2 Ω @ 10 V; 1.8 Ω @ 4.5 V | 1.12 Ω; 2.06 Ω |
| | | Ciss / Coss / Crss 20 / 11 / 4 pF @ 25 V | 19.5 / 10.4 / 3.5 pF |
| `BS250_OJ` PMOS | BS250 | VGS(th) −2.4 V; RDS(on) ≈ 9 Ω @ −10 V | −2.4 V; 8.9 Ω |
| `1N4148_OJ` | 1N4148, 1N914 | VF 0.61 / 0.72 / 0.92 V @ 1 / 10 / 100 mA | 0.611 / 0.729 / 0.920 V |
| | | trr ≤ 4 ns (10 mA → 10 mA → 1 mA) | 3.97 ns |
| `1N5819_OJ` Schottky | 1N5819 | VF 0.30 / 0.42 / 0.55 V @ 0.1 / 1 / 3 A | 0.306 / 0.419 / 0.563 V |
| `BZX79C{3V3,4V7,5V1,5V6,6V2,9V1,12,15}_OJ` | BZX79 / BZX55 500 mW | VZ and rZ at IZT = 5 mA | exact by construction |
| `1N4733A_OJ`, `1N4742A_OJ` | 1N47xxA 1 W | 5.1 V / 12 V at datasheet IZT | exact by construction |
| `TL07X_OJ` (one section) | TL071/072/074 | AOL 106 dB, GBW 3 MHz, SR 13 V/µs | 106 dB, 2.9 MHz (57° PM), 12.9 V/µs |
| | | ±13.5 V into 10 kΩ @ ±15 V, IQ 1.4 mA | ±13.38 V, 1.4 mA |
| `LM358_OJ` (one section) | LM358, LM324 | GBW 0.7 MHz, SR 0.3 V/µs, AOL 100 dB | 0.72 MHz, 0.3 V/µs, 100 dB |
| | | swings to ~V− at light load, V+ − 1.5 V | 6 mV / V+ − 1.52 V into 10 kΩ |

Rerun every check with `python tests/validate.py`, or name models to check only
those. It needs ngspice 47 or later and Python 3.13 or later, with nothing to install from pip. If
ngspice isn't on your `PATH`, set the `NGSPICE` environment variable to its location.

The targets and tolerances live in [`tests/models.toml`](tests/models.toml). See
[CONTRIBUTING.md](CONTRIBUTING.md) to add a model.

## Limits — read before trusting a result

* These are *typical* devices. Real parts spread widely (BC547 hFE spans
  110–800 across groups; 2N7000 VGS(th) spans 0.8–3 V). Run corners by
  editing BF, VTO etc.
* BJTs: no breakdown or quasi-saturation modelled. Temperature uses standard
  SPICE coefficients (not fitted).
* MOSFETs use the VDMOS model (ngspice ≥ 47, LTspice). For PSpice you would need
  a subcircuit rewrite.
* Zeners: VZ temperature coefficient and noise not modelled; knee shape is
  approximate.
* Op-amps: no input common-mode range limits or phase reversal, no noise,
  CMRR/PSRR, offset drift, or LM358 crossover distortion. VOS defaults to 0 —
  use `OPAMP_OJ params: VOS=3m ...` to add offset.
* Tested in ngspice 47 only; LTspice should accept the syntax
  but hasn't been run.
