"""mwr_l12l2: Tools for running optimal estimation retrievals for ground-based microwave radiometers."""

# Import key classes/functions for convenience
from mwr_l12l2.retrieval.retrieval import Retrieval
from mwr_l12l2.retrieval.retrieval_manager import RetrievalManager

import importlib.metadata

__version__ = importlib.metadata.version("mwr_l12l2")

__all__ = [
    "__version__",
    "Retrieval",
]
