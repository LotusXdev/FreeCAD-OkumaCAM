"""Unit tests for tool change sequences and G111 (OTCHK / TOOLCHK.LIB) tool check integration."""

from __future__ import annotations

import unittest
import FreeCAD as App
import Path
import OkumaOSP_post


class MockToolController:
    """Mock FreeCAD ToolController."""

    def __init__(self, tool_number: int = 1, spindle_speed: int = 3500, spindle_dir: str = "CW"):
        self.ToolNumber = tool_number
        self.SpindleSpeed = spindle_speed
        self.SpindleDir = spindle_dir


class MockOperation:
    """Mock FreeCAD Path Operation."""

    def __init__(self, name: str = "Op1", tool_number: int = 1):
        self.Name = name
        self.Label = name
        self.ToolController = MockToolController(tool_number=tool_number)
        cmd1 = Path.Command("G0", {"X": 0.0, "Y": 0.0, "Z": 5.0})
        cmd2 = Path.Command("G1", {"X": 10.0, "Y": 0.0, "Z": -1.0, "F": 20.0})
        self.Path = Path.Path([cmd1, cmd2])


class TestToolChangeMacro(unittest.TestCase):
    """Test cases for Okuma tool change and G111 OTCHK tool check invocation."""

    def test_toolchange_with_toolcheck_enabled(self):
        """Verify that G111 T_ is emitted when tool check is enabled."""
        op = MockOperation(name="Facing", tool_number=2)
        gcode, _ = OkumaOSP_post.export([op], filename="-", argstring="--toolcheck")

        self.assertIn("NAT01", gcode)
        self.assertIn("T2 M6", gcode)
        self.assertIn("G15 H1", gcode)
        self.assertIn("G56 H2", gcode)
        # Dedicated G111 call to OTCHK in TOOLCHK.LIB
        self.assertIn("G111 T2", gcode)
        self.assertIn("S3500 M3", gcode)
        self.assertIn("M8", gcode)

    def test_toolchange_with_toolcheck_disabled(self):
        """Verify that G111 is not emitted when tool check is disabled."""
        op = MockOperation(name="Contour", tool_number=3)
        gcode, _ = OkumaOSP_post.export([op], filename="-", argstring="--no-toolcheck")

        self.assertIn("T3 M6", gcode)
        self.assertIn("G56 H3", gcode)
        self.assertNotIn("G111", gcode)

    def test_multiple_toolchanges(self):
        """Verify sequential tool sequence blocks NAT01, NAT02."""
        op1 = MockOperation(name="Roughing", tool_number=1)
        op2 = MockOperation(name="Finishing", tool_number=4)

        gcode, _ = OkumaOSP_post.export([op1, op2], filename="-", argstring="--toolcheck")
        self.assertIn("NAT01", gcode)
        self.assertIn("T1 M6", gcode)
        # Verify next tool Q4 is staged per TOOLCHK.LIB specification
        self.assertIn("G111 T1 Q4", gcode)

        self.assertIn("NAT02", gcode)
        self.assertIn("T4 M6", gcode)
        # Final tool has no subsequent tool, so Q is omitted
        self.assertIn("G111 T4", gcode)

    def test_spindle_ccw_m4(self):
        """Verify CCW spindle direction emits M4."""
        op = MockOperation(name="Tapping", tool_number=5)
        op.ToolController.SpindleDir = "CCW"
        op.ToolController.SpindleSpeed = 800
        gcode, _ = OkumaOSP_post.export([op], filename="-")
        self.assertIn("S800 M4", gcode)

    def test_three_tool_lookahead_staging(self):
        """Verify 3-tool sequence stages next tool properly: T1 Q2 -> T2 Q3 -> T3."""
        op1 = MockOperation(name="Op1", tool_number=1)
        op2 = MockOperation(name="Op2", tool_number=2)
        op3 = MockOperation(name="Op3", tool_number=3)

        gcode, _ = OkumaOSP_post.export([op1, op2, op3], filename="-", argstring="--toolcheck")
        self.assertIn("G111 T1 Q2", gcode)
        self.assertIn("G111 T2 Q3", gcode)
        self.assertIn("G111 T3", gcode)
        # T3 must not have a Q argument
        self.assertNotIn("G111 T3 Q", gcode)

    def test_default_spindle_fallback(self):
        """Verify fallback to 1000 RPM CW when speed is 0."""
        op = MockOperation(name="DefaultOp", tool_number=6)
        op.ToolController.SpindleSpeed = 0
        gcode, _ = OkumaOSP_post.export([op], filename="-")
        self.assertIn("S1000 M3", gcode)


if __name__ == "__main__":
    unittest.main()

