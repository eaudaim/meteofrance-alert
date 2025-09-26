"""PlantAlert package initialization."""

from importlib import metadata

__all__ = ["__version__"]

try:
    __version__ = metadata.version("plantalert")
except metadata.PackageNotFoundError:  # pragma: no cover - version absent en dev
    __version__ = "0.1.0"
