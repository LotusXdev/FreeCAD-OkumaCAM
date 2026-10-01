"""OkumaCAM Test Suite Package.

Ensures the OkumaCAM package root is on sys.path during test discovery.
"""

import os
import sys

_pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)
