"""Integration tests for OkumaContourPocket operation and post-processor emission."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import FreeCAD as App
try:
    import OkumaOSP_post
except ImportError:
    from OkumaCAM import OkumaOSP_post
try:
    from OkumaCAM.Op.ContourPocket import ContourPocket, Create as CreateContourPocket
except ImportError:
    from Op.ContourPocket import ContourPocket, Create as CreateContourPocket


class TestContourPocket(unittest.TestCase):
    """Test suite for OkumaContourPocket operation."""

    def setUp(self):
        self.doc = App.newDocument("TestPocketDoc")
        self.temp_dir = tempfile.mkdtemp()
        OkumaOSP_post.reset_defaults()

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_mock_tool_controller(self, name: str, tool_num: int, dia: float = 10.0, feed: float = 20.0):
        tc = self.doc.addObject("Path::FeaturePython", name)
        tc.addProperty("App::PropertyInteger", "ToolNumber", "Tool", "Tool number")
        tc.ToolNumber = tool_num
        tc.addProperty("App::PropertyDistance", "Diameter", "Tool", "Tool diameter")
        tc.Diameter = dia
        tc.addProperty("App::PropertySpeed", "HorizFeed", "Tool", "Feedrate")
        tc.HorizFeed = feed  # 20 mm/s = 1200 mm/min
        tc.addProperty("App::PropertyFloat", "SpindleSpeed", "Tool", "Spindle speed")
        tc.SpindleSpeed = 3500.0
        return tc

    def test_pocket_property_defaults(self):
        """Verify ContourPocket object properties and default values."""
        op = CreateContourPocket("PocketOp")
        self.assertEqual(op.Proxy.Type, "OkumaContourPocket")
        self.assertEqual(str(op.PocketStrategy), "Auto")
        self.assertAlmostEqual(float(getattr(op.InscribedMinCoverage, "Value", op.InscribedMinCoverage)), 0.40)
        self.assertEqual(str(op.RoughCycle), "PMILR (Spiral)")
        self.assertEqual(str(op.FinishCycle), "RMILI (Perimeter)")
        self.assertTrue(bool(op.EnableFinishing))

    def test_dual_tool_rectangular_pocket_export(self):
        """Verify rectangular pocket exports PMILR for roughing, G111 staging, and RMILI for finishing."""
        tc_rough = self._create_mock_tool_controller("TC_Rough", 1, dia=12.0)
        tc_finish = self._create_mock_tool_controller("TC_Finish", 2, dia=10.0)

        op = CreateContourPocket("RectPocket")
        op.RoughingTool = tc_rough
        op.FinishingTool = tc_finish
        op.StartDepth = 0.0
        op.FinalDepth = -20.0
        op.RoughStepDown = 3.0
        op.FinishStepDown = 1.0
        op.FinishAllowance = 0.5
        op.Proxy.boundary_points = [(0.0, 0.0), (100.0, 0.0), (100.0, 60.0), (0.0, 60.0)]

        op.Proxy.execute(op)
        self.assertEqual(op.InscribedCoreType, "RECTANGLE")
        self.assertAlmostEqual(float(op.InscribedCoverage), 1.0, places=2)

        out_min = os.path.join(self.temp_dir, "RECT_POCKET.MIN")
        main_code, sub_code = OkumaOSP_post.export([op], filename=out_min, argstring="--toolcheck")

        self.assertTrue(os.path.exists(out_min))
        with open(out_min, "r", encoding="utf-8") as f:
            content = f.read()

        # 1. Staging check: T1 stages Q2 via G111
        self.assertIn("NAT01", content)
        self.assertIn("T1 M6", content)
        self.assertIn("G111 T1 Q2", content)

        # 2. Canned cycle roughing check: PMILR with K.5
        self.assertIn("PMILR", content)
        self.assertIn("K.5", content)
        self.assertIn("Z-20.", content)

        # 3. Finishing pass check: T2 stages T1 (or stands alone) and emits RMILI with K0.
        self.assertIn("NAT02", content)
        self.assertIn("T2 M6", content)
        self.assertIn("RMILI", content)
        self.assertIn("D2", content)

    def test_hybrid_inscribed_l_shape_pocket_export(self):
        """Verify L-shaped cavity decomposes into PMILR core + residual subprogram."""
        tc_rough = self._create_mock_tool_controller("TC_Rough", 3, dia=10.0)
        tc_finish = self._create_mock_tool_controller("TC_Finish", 4, dia=8.0)

        op = CreateContourPocket("LPocket")
        op.RoughingTool = tc_rough
        op.FinishingTool = tc_finish
        op.StartDepth = 0.0
        op.FinalDepth = -15.0
        op.RoughStepDown = 2.5
        # L-shape: 100x100 minus top-right 50x50 block
        op.Proxy.boundary_points = [
            (0.0, 0.0),
            (100.0, 0.0),
            (100.0, 50.0),
            (50.0, 50.0),
            (50.0, 100.0),
            (0.0, 100.0),
        ]

        op.Proxy.execute(op)
        self.assertEqual(op.InscribedCoreType, "RECTANGLE")
        self.assertTrue(float(op.InscribedCoverage) > 0.60)
        self.assertTrue(len(op.Proxy.residual_commands) > 0)

        out_min = os.path.join(self.temp_dir, "L_POCKET.MIN")
        main_code, sub_code = OkumaOSP_post.export([op], filename=out_min, argstring="--toolcheck")

        with open(out_min, "r", encoding="utf-8") as f:
            content = f.read()

        # Check core canned cycle emitted
        self.assertIn("PMILR", content)
        # Check residual subprogram call loop emitted
        self.assertIn("CALL O", content)
        self.assertIn("PZ=[LA]", content)
        self.assertIn("PR=2.", content)

        # Check that .SUB file was generated with RTS
        sub_path = os.path.join(self.temp_dir, "L_POCKET.SUB")
        self.assertTrue(os.path.exists(sub_path))
        with open(sub_path, "r", encoding="utf-8") as f:
            sub_content = f.read()
        self.assertTrue(sub_content.startswith("O"))
        self.assertIn("RTS", sub_content)

    def test_circular_inscribed_core_pocket_export(self):
        """Verify circular pocket emits circular/helical cycle for core."""
        import math
        n_pts = 32
        poly = [
            (35.0 * math.cos(i * 2.0 * math.pi / n_pts),
             35.0 * math.sin(i * 2.0 * math.pi / n_pts))
            for i in range(n_pts)
        ]

        tc_rough = self._create_mock_tool_controller("TC_Rough", 5, dia=10.0)
        op = CreateContourPocket("CircPocket")
        op.RoughingTool = tc_rough
        op.EnableFinishing = False
        op.StartDepth = 0.0
        op.FinalDepth = -12.0
        op.Proxy.boundary_points = poly

        op.Proxy.execute(op)
        self.assertEqual(op.InscribedCoreType, "CIRCLE")

        out_min = os.path.join(self.temp_dir, "CIRC_POCKET.MIN")
        main_code, _ = OkumaOSP_post.export([op], filename=out_min)

        with open(out_min, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("G2", content)
        self.assertIn("Z-12.", content)


if __name__ == "__main__":
    unittest.main()
