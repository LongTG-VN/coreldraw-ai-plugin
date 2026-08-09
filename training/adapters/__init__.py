"""Source-specific adapters into the unified design schema."""

from training.adapters.base import AdapterError, DesignAdapter
from training.adapters.genposter import GenPosterAdapter

__all__ = ["AdapterError", "DesignAdapter", "GenPosterAdapter"]
