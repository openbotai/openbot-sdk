from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("openbot-sdk")
except PackageNotFoundError:  # pragma: no cover - raw source tree without installation
    __version__ = "0+unknown"
