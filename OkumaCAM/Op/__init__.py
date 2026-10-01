"""OkumaCAM Operations Package.

Provides Okuma-optimized CAM operations for FreeCAD:
- ContourPocket: Inscribed volume canned cycles & residual subprograms
- ContourSurfacing: Face milling canned cycles & waterline subprograms
"""

from __future__ import annotations

from OkumaCAM.Op.ContourPocket import ContourPocket
from OkumaCAM.Op.ContourSurfacing import ContourSurfacing

__all__ = ["ContourPocket", "ContourSurfacing"]
