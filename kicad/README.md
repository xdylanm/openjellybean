# openjellybean KiCad symbols

Schematic symbols for every model in `jellybean.lib` except the potentiometer (KiCad's
own potentiometer symbol covers that). Each symbol carries the `Sim.*` fields that
tie it to its `_OJ` model, so it simulates in KiCad 8 and later with no further setup.
There are no footprints or 3D models.

| Library | Symbols |
|---|---|
| `OpenJellybean_BJT` | `BC547B_OJ`, `BC557B_OJ`, `2N3904_OJ`, `2N3906_OJ` |
| `OpenJellybean_FET` | `2N7000_OJ`, `BS250_OJ`, and the N and P JFETs |
| `OpenJellybean_Diode` | `1N4148_OJ`, Schottky diodes, zeners (`ZENER_OJ`, `BZX79C*`, `1N47xxA`), LEDs |
| `OpenJellybean_Amplifier` | `OPAMP_OJ`, `TL07X_OJ`, `LM358_OJ`, and the complete `TL072`, `TL074`, `LM358_DUAL`, `LM324_QUAD` packages |

Package op-amps are multi-unit symbols whose pin numbers are the real package pins.
Everything else numbers its pins in SPICE order (BJT `C B E`, FET `D G S`, diode `K A`
as in KiCad's stock symbols), and the `Sim.Pins` field does the mapping.

## Install

1. Install the package, or clone the repository, and find the folder that holds
   `jellybean.lib`:

   ```bash
   pip install openjellybean
   python -m openjellybean
   ```

2. In KiCad, open **Preferences > Configure Paths** and add the variable
   `OPENJELLYBEAN_DIR`, set to the folder that holds `jellybean.lib` (the symbols'
   `Sim.Library` field is `${OPENJELLYBEAN_DIR}/jellybean.lib`).

3. Open **Preferences > Manage Symbol Libraries** and add the four `OpenJellybean_*.kicad_sym`
   files, from the `symbols` folder that `python -m openjellybean` prints.

## Regenerating

The libraries are generated, not drawn by hand. After you add or change a model in
`jellybean.lib` and `tests/models.toml`, run:

```bash
python tools/gen_symbols.py
```

It reads the stock KiCad symbols from your KiCad install (set `KICAD_SYMBOL_DIR` or pass
`--kicad-symbols` if it isn't in the usual place), so commit the output of the
KiCad 9 libraries. `python tools/gen_symbols.py --check` reports stale files. To add a
device kind, map it to a stock symbol in `BASE` and to a library in `LIBRARY_OF_KIND`.

## License

The symbols are copies of KiCad symbols, so they are licensed
**CC-BY-SA 4.0 with the KiCad libraries exception**, unlike the MIT-licensed models.
See [LICENSE.md](LICENSE.md).
