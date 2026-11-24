"""openjellybean: generic "jelly bean" SPICE models and matching KiCad symbols.

Use :func:`library_path` to locate ``jellybean.lib`` for ``.include``/``.lib``
lines or for tools that take a model file path, and :func:`symbols_path` to locate
the folder of KiCad symbol libraries (``OpenJellybean_*.kicad_sym``).
"""

from __future__ import annotations

from importlib import resources
from importlib.metadata import PackageNotFoundError, version as _version
from pathlib import Path

try:
    __version__ = _version("openjellybean")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0+unknown"

__all__ = ["__version__", "library_path", "symbols_path"]


def library_path() -> Path:
    """Return the filesystem path of the bundled ``jellybean.lib``.

    The package is installed unzipped, so the resource is a real file.
    """
    return Path(str(resources.files(__package__).joinpath("jellybean.lib")))


def symbols_path() -> Path:
    """Return the folder holding the ``OpenJellybean_*.kicad_sym`` KiCad symbol libraries.

    The symbols are licensed CC-BY-SA 4.0 with the KiCad libraries exception, unlike the
    MIT-licensed models; the license text is the ``LICENSE.md`` in the same folder.
    """
    return Path(str(resources.files(__package__).joinpath("symbols")))
