"""Structured design inference contracts and Corel compilation."""

from training.inference.baseline import generate_baseline_design
from training.inference.corel_compiler import CorelCompileError, compile_corel_operations

__all__ = [
    "CorelCompileError",
    "compile_corel_operations",
    "generate_baseline_design",
]
