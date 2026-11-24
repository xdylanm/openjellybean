"""``python -m openjellybean`` prints where the bundled files are."""

from . import __version__, library_path, symbols_path

print(f"openjellybean {__version__}")
print(f"SPICE library: {library_path()}")
print(f"  set the KiCad path variable OPENJELLYBEAN_DIR to: {library_path().parent}")
print(f"KiCad symbol libraries: {symbols_path()}")
