### openjellybean KiCad symbol libraries: license

The symbol libraries in [`symbols/`](symbols) (`OpenJellybean_*.kicad_sym`) are
modified copies of symbols from the KiCad symbol libraries
(<https://gitlab.com/kicad/libraries/kicad-symbols>), which are copyright the KiCad
Library Team and contributors. They are therefore licensed as the KiCad libraries are:

SPDX-License-Identifier: `CC-BY-SA-4.0 WITH KiCad-libraries-exception`

The [Creative Commons CC-BY-SA 4.0 License](https://creativecommons.org/licenses/by-sa/4.0/legalcode),
with the following exception:

---------

_To the extent that the creation of electronic designs that use 'Licensed Material' can be considered to be 'Adapted Material', then the copyright holder waives article 3 of the license with respect to these designs and any generated files which use data provided as part of the 'Licensed Material'._

---------

This is the exception text of the KiCad libraries license (<https://www.kicad.org/libraries/license/>).

**What does this mean?**

Using these symbols in your own design does not (by itself) require that the design or
any files generated from it are licensed under CC-BY-SA 4.0, and you do not have to
attribute the libraries within your design.

If you redistribute these libraries, or parts of them (including in modified form) as a
collection, the exception above does not apply. Redistributed collections must be shared
under the same license, and must keep this file and the attribution it contains.

**Changes from the KiCad libraries**

Each symbol's graphics and pins are copied from a stock KiCad symbol (`Device`,
`Transistor_BJT`, `Transistor_FET`, `Simulation_SPICE` and `Amplifier_Operational`),
renamed, and given the `Sim.*` fields that connect it to `jellybean.lib`. The footprint
and footprint-filter fields are removed. `tools/gen_symbols.py` makes the changes.

**Scope**

This license covers only the files in this directory. The SPICE models, `jellybean.lib`,
the test framework, the generator and the Python package code are under the
[MIT license](../LICENSE).

**Warranty**

These libraries are provided in the hope that they will be useful, but are provided
without warranty of any kind, express or implied.
