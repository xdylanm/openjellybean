# openjellybean KiCad symbols

Schematic symbols for every model in `jellybean.lib` except the potentiometer (KiCad's
own potentiometer symbol covers that). Each symbol carries the `Sim.*` fields that
tie it to its `_OJ` model, so it simulates in KiCad 9 or later once `OPENJELLYBEAN_DIR`
is set (see [Install](#install)). There are no footprints or 3D models.

| Library | Symbols |
|---|---|
| `OpenJellybean_BJT` | `BC547B_OJ`, `BC557B_OJ`, `2N3904_OJ`, `2N3906_OJ` |
| `OpenJellybean_FET` | `2N7000_OJ`, `BS250_OJ`, and the N and P JFETs |
| `OpenJellybean_Diode` | `1N4148_OJ`, Schottky diodes, zeners (`ZENER_OJ`, `BZX79C*`, `1N47xxA`), LEDs |
| `OpenJellybean_Amplifier` | `OPAMP_OJ`, `TL07X_OJ`, `LM358_OJ`, and the complete `TL072`, `TL074`, `LM358_DUAL`, `LM324_QUAD` packages |

Package op-amps are multi-unit symbols whose pin numbers are the real package pins.
Everything else keeps the pin numbering of KiCad's stock symbols (BJT 1=C 2=B 3=E,
FET 1=D 2=G 3=S, diode 1=K 2=A), and the `Sim.Pins` field maps those to the model's
nodes, so the SPICE node order is always right.

The files are in KiCad 9 format, generated from the stock libraries of KiCad release
**9.0.9**.

## Install

Two things are needed: the four symbol libraries, and a KiCad path variable that tells
the simulator where `jellybean.lib` is (the symbols' `Sim.Library` field is
`${OPENJELLYBEAN_DIR}/jellybean.lib`).

1. Find the two locations.

   *Installed from PyPI* (`pip install openjellybean`): run `python -m openjellybean`,
   which prints the folder to use for `OPENJELLYBEAN_DIR` and the folder holding the
   symbol libraries.

   *Cloned from git*: `OPENJELLYBEAN_DIR` is the repository root (where `jellybean.lib`
   is), and the symbol libraries are in `kicad/symbols`. (`pip install -e .` also works
   and `python -m openjellybean` then prints these paths.)

2. In KiCad, open **Preferences > Configure Paths** and add the variable
   `OPENJELLYBEAN_DIR`, set to that folder. It must be an **absolute path**, such as
   `/home/you/src/openjellybean`: KiCad does not expand `~` or relative paths, and the
   simulator then fails to find `jellybean.lib`.

3. Open **Preferences > Manage Symbol Libraries** and add the four
   `OpenJellybean_*.kicad_sym` files.

## Regenerating

The libraries are generated, not drawn by hand. After you add or change a model in
`jellybean.lib` and `tests/models.toml`, run:

```bash
python tools/gen_symbols.py
```

It copies graphics from the stock KiCad 9 symbols, so it needs a KiCad 9 install or a
checkout of [kicad-symbols](https://gitlab.com/kicad/libraries/kicad-symbols). It looks
for them, in order, at:

1. the `--kicad-symbols DIR` option,
2. the `KICAD_SYMBOL_DIR` or `KICAD9_SYMBOL_DIR` environment variable,
3. the usual install locations on Linux (including Flatpak), macOS and Windows.

If KiCad is somewhere else, point the option or variable at the folder that contains
`Device.kicad_sym`. It refuses stock libraries that are not KiCad 9.

`python tools/gen_symbols.py --check` reports stale, missing or extra files. The committed
files come from kicad-symbols **9.0.9**, and CI checks them against that tag. Stock
symbols from another 9.0.x release can differ slightly, so if `--check` reports changes
you did not make, compare against a 9.0.9 checkout before committing regenerated files.

To add a device kind, map it to a stock symbol in `BASE` and to a library in
`LIBRARY_OF_KIND`.

## License

The symbols are copies of KiCad symbols, so the `OpenJellybean_*.kicad_sym` files are
licensed **CC-BY-SA 4.0 with the KiCad libraries exception**, unlike the MIT-licensed
models. See [LICENSE.md](LICENSE.md).
