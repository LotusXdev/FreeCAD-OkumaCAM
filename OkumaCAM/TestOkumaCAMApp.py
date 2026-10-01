"""OkumaCAM Test Suite Registration Module for FreeCAD.

Exposes all OkumaCAM unit and integration test cases to FreeCAD's built-in
test framework (FreeCAD.__unit_test__ and FreeCADCmd -t TestOkumaCAMApp).
"""

from __future__ import annotations

import os
import sys

_mod_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_mod_dir)
for p in (_parent_dir, _mod_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

from tests.test_compression import TestGCodeCompressor
from tests.test_modal import TestModalTracker
from tests.test_patterns import TestPatternRecognizer
from tests.test_area_machining import TestAreaMachining
from tests.test_toolchange_macro import TestToolChangeMacro
from tests.test_post_integration import TestPostIntegration
from tests.test_gui import TestOkumaCAMPreferences
from tests.test_zslice_subprograms import TestZSliceSubprograms
from tests.test_inscribed_volume import TestInscribedVolume
from tests.test_contour_pocket import TestContourPocket
from tests.test_contour_surfacing import TestContourSurfacing
from tests.test_electric_speeder import TestElectricSpeeder
from tests.test_separate_rough_finish import TestSeparateRoughFinish

try:
    from tests.test_gui import TestOkumaCAMGuiCommands
except ImportError:
    TestOkumaCAMGuiCommands = None

__all__ = [
    "TestGCodeCompressor",
    "TestModalTracker",
    "TestPatternRecognizer",
    "TestAreaMachining",
    "TestToolChangeMacro",
    "TestPostIntegration",
    "TestOkumaCAMPreferences",
    "TestZSliceSubprograms",
    "TestInscribedVolume",
    "TestContourPocket",
    "TestContourSurfacing",
    "TestElectricSpeeder",
    "TestSeparateRoughFinish",
]
if TestOkumaCAMGuiCommands is not None:
    __all__.append("TestOkumaCAMGuiCommands")
