"""Integration tests for OkumaContourSurfacing operation and post-processor emission."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import Path
try:
    import OkumaOSP_post
except ImportError:
    from OkumaCAM import OkumaOSP_post
try:
    from OkumaCAM.Op.ContourSurfacing import ContourSurfacing, Create as CreateContourSurfacing
except ImportError:
    from Op.ContourSurfacing import ContourSurfacing, Create as CreateContourSurfacing


class TestContourSurfacing(unittest.TestCase):
    """Test suite for OkumaContourSurfacing operation."""

    def setUp(self):
        self.doc = App.newDocument("TestSurfDoc")
        self.temp_dir = tempfile.mkdtemp()
        OkumaOSP_post.reset_defaults()

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_mock_tool_controller(self, name: str, tool_num: int, dia: float = 50.0, feed: float = 25.0):
        tc = self.doc.addObject("Path::FeaturePython", name)
        tc.addProperty("App::PropertyInteger", "ToolNumber", "Tool", "Tool number")
        tc.ToolNumber = tool_num
        tc.addProperty("App::PropertyDistance", "Diameter", "Tool", "Tool diameter")
        tc.Diameter = dia
        tc.addProperty("App::PropertySpeed", "HorizFeed", "Tool", "Feedrate")
        tc.HorizFeed = feed  # 25 mm/s = 1500 mm/min
        tc.addProperty("App::PropertyFloat", "SpindleSpeed", "Tool", "Spindle speed")
        tc.SpindleSpeed = 2200.0
        return tc

    def test_surfacing_property_defaults(self):
        """Verify ContourSurfacing object properties and default values."""
        op = CreateContourSurfacing("SurfOp")
        self.assertEqual(op.Proxy.Type, "OkumaContourSurfacing")
        self.assertEqual(str(op.SurfacingStrategy), "Auto")
        self.assertEqual(str(op.FacingPattern), "Zigzag (FMILR)")
        self.assertTrue(bool(op.EnableFinishing))
        self.assertAlmostEqual(float(getattr(op.RoughStepOver, "Value", op.RoughStepOver)), 75.0)

    def test_planar_face_surfacing_dual_tool_export(self):
        """Verify planar face surfacing exports FMILR for roughing, stages finish tool, and FMILF for finish."""
        tc_rough = self._create_mock_tool_controller("TC_RoughFace", 1, dia=50.0)
        tc_finish = self._create_mock_tool_controller("TC_FinishFace", 2, dia=63.0)

        op = CreateContourSurfacing("PlanarFaceOp")
        op.RoughingTool = tc_rough
        op.FinishingTool = tc_finish
        op.StartDepth = 0.0
        op.FinalDepth = -4.0
        op.RoughStepDown = 2.0
        op.FinishStepDown = 0.5
        op.FinishAllowance = 0.25

        op.Proxy.mock_bounds = {
            "is_planar": True,
            "xmin": 10.0,
            "ymin": 20.0,
            "xlen": 100.0,
            "ylen": 60.0,
            "zmin": -4.0,
            "zmax": 0.0,
        }
        op.Proxy.execute(op)

        out_min = os.path.join(self.temp_dir, "SURF_FACE.MIN")
        main_code, _ = OkumaOSP_post.export([op], filename=out_min, argstring="--toolcheck")

        self.assertTrue(os.path.exists(out_min))
        with open(out_min, "r", encoding="utf-8") as f:
            content = f.read()

        # 1. Staging check: T1 stages Q2
        self.assertIn("NAT01", content)
        self.assertIn("T1 M6", content)
        self.assertIn("G111 T1 Q2", content)

        # 2. Roughing canned cycle check: FMILR with K.25
        self.assertIn("FMILR", content)
        self.assertIn("X10.", content)
        self.assertIn("Y20.", content)
        self.assertIn("I100.", content)
        self.assertIn("J60.", content)
        self.assertIn("K.25", content)
        self.assertIn("Z-4.", content)

        # 3. Finishing canned cycle check: T2 emits FMILF with K0.
        self.assertIn("NAT02", content)
        self.assertIn("T2 M6", content)
        self.assertIn("FMILF", content)
        self.assertIn("D2", content)

    def test_surfacing_single_tool_roughing_only(self):
        """Verify surfacing with EnableFinishing=False omits NAT02 and FMILF."""
        tc_rough = self._create_mock_tool_controller("TC_RoughOnly", 5, dia=50.0)

        op = CreateContourSurfacing("RoughOnlyOp")
        op.RoughingTool = tc_rough
        op.EnableFinishing = False
        op.StartDepth = 0.0
        op.FinalDepth = -2.0

        op.Proxy.execute(op)

        out_min = os.path.join(self.temp_dir, "ROUGH_ONLY.MIN")
        main_code, _ = OkumaOSP_post.export([op], filename=out_min)

        with open(out_min, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("FMILR", content)
        self.assertNotIn("FMILF", content)
        self.assertNotIn("NAT02", content)


if __name__ == "__main__":
    unittest.main()
