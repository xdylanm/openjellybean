"""openjellybean: generic "jelly bean" SPICE models.

Use :func:`library_path` to locate ``jellybean.lib`` for ``.include``/``.lib``
lines or for tools that take a model file path.
"""

from __future__ import annotations

from importlib import resources
from importlib.metadata import PackageNotFoundError, version as _version
from pathlib import Path

try:
    __version__ = _version("openjellybean")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0+unknown"

__all__ = ["__version__", "library_path"]


def library_path() -> Path:
    """Return the filesystem path of the bundled ``jellybean.lib``.

    The package is installed unzipped, so the resource is a real file.
    """
    return Path(str(resources.files(__package__).joinpath("jellybean.lib")))
