"""OkumaCAM Non-GUI Initialization Module.

Registers OkumaOSP post-processor and optimization modules into FreeCAD
headless environment and sys.path for CLI, batch, and test execution.
"""

from __future__ import annotations

import os
import sys

try:
    _mod_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _mod_dir = os.path.abspath(".")
    for p in sys.path:
        if os.path.exists(os.path.join(p, "OkumaOSP_post.py")):
            _mod_dir = p
            break

if _mod_dir not in sys.path:
    sys.path.insert(0, _mod_dir)


try:
    import FreeCAD as App
    App.Console.PrintLog("OkumaCAM: Initialized non-GUI post-processor module.\n")
    if hasattr(App, "__unit_test__"):
        if "TestOkumaCAMApp" not in App.__unit_test__:
            App.__unit_test__ += ["TestOkumaCAMApp"]
except Exception:
    pass

