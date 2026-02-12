"""mwr_l12l2: Tools for running optimal estimation retrievals for ground-based microwave radiometers."""

import importlib.metadata

# Import key classes/functions for convenience
from mwr_l12l2.retrieval.retrieval import Retrieval

__version__ = importlib.metadata.version("mwr_l12l2")

__all__ = [
    "__version__",
    "Retrieval",
]
