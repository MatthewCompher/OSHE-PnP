"""pnpslice: turns a KiCad board into pick-and-place job files (oshe-pnp-job/1)."""

from .board import Board, Footprint, Pad, BoardError, load_board

__all__ = ["Board", "Footprint", "Pad", "BoardError", "load_board"]
__version__ = "0.1.0"