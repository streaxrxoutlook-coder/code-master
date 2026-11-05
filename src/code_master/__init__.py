"""Local, deterministic code intelligence."""

from code_master.analyze import analyze
from code_master.model import Report
from code_master.version import __version__

__all__ = ["Report", "__version__", "analyze"]
