"""Integration tests for OkumaOSP_post with real FreeCAD CAM objects."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import Path
import OkumaOSP_post


class TestPostIntegration(unittest.TestCase):
    """Integration test suite executing post-processing against FreeCAD objects."""

    def setUp(self):
        self.doc = App.newDocument("TestOkumaDoc")
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_end_to_end_post_export_metric(self):
        """Verify full export creates valid .MIN file with converted units."""
        # Create Path feature
        feat = self.doc.addObject("Path::Feature", "TestPath")
        cmd_rapid = Path.Command("G0", {"X": 0.0, "Y": 0.0, "Z": 10.0})
        # Note: 20 mm/s = 1200 mm/min
        cmd_cut = Path.Command("G1", {"X": 50.0, "Y": 25.0, "Z": -2.0, "F": 20.0})
        feat.Path = Path.Path([cmd_rapid, cmd_cut])

        out_min = os.path.join(self.temp_dir, "O1234.MIN")
        main_code, _ = OkumaOSP_post.export([feat], filename=out_min, argstring="--metric --toolcheck")

        self.assertTrue(os.path.exists(out_min))
        with open(out_min, "r", encoding="utf-8") as f:
            content = f.read()

        # Check program number from filename
        self.assertTrue(content.startswith("O1234"))
        # Check units
        self.assertIn("G21", content)
        # Check feedrate converted from 20 mm/s to 1200 mm/min
        self.assertIn("F1200.", content)
        # Check tool check macro
        self.assertIn("G111", content)
        # Check safety shutdown
        self.assertIn("M02", content)

    def test_end_to_end_post_export_imperial(self):
        """Verify imperial export converts feedrate to IPM."""
        feat = self.doc.addObject("Path::Feature", "TestPathImp")
        # 10 mm/s = 600 mm/min = 23.622 in/min
        cmd = Path.Command("G1", {"X": 2.0, "Y": 1.0, "Z": -0.1, "F": 10.0})
        feat.Path = Path.Path([cmd])

        out_min = os.path.join(self.temp_dir, "O2000.MIN")
        main_code, _ = OkumaOSP_post.export([feat], filename=out_min, argstring="--inches --no-toolcheck")

        self.assertIn("G20", main_code)
        # 10 mm/s converted to in/min is ~23.6
        self.assertIn("F23.6", main_code)
        self.assertNotIn("G111", main_code)

    def test_subprogram_file_creation(self):
        """Verify that enabling subprograms creates a separate .SUB file."""
        feat = self.doc.addObject("Path::Feature", "ContourProfile")
        cmds = [
            Path.Command("G1", {"X": 0.0, "Y": 0.0, "Z": -1.0, "F": 15.0}),
            Path.Command("G1", {"X": 20.0, "Y": 0.0}),
            Path.Command("G1", {"X": 20.0, "Y": 20.0}),
            Path.Command("G1", {"X": 0.0, "Y": 20.0}),
            Path.Command("G1", {"X": 0.0, "Y": 0.0}),
        ]
        feat.Path = Path.Path(cmds)

        out_min = os.path.join(self.temp_dir, "Part1.MIN")
        main_code, sub_code = OkumaOSP_post.export(
            [feat], filename=out_min, argstring="--subprograms"
        )

        out_sub = os.path.join(self.temp_dir, "Part1.SUB")
        self.assertTrue(os.path.exists(out_sub))

        with open(out_sub, "r", encoding="utf-8") as f:
            sub_content = f.read()

        self.assertIn("O0100", sub_content)
        self.assertTrue(sub_content.strip().endswith("RTS"))
        # Main program must contain CALL O0100
        self.assertIn("CALL O0100", main_code)

    def test_export_facing_operation_native_fmilr(self):
        """Verify CAM Facing operation with bounding box produces native FMILR command."""
        class MockBoundBox:
            XMin = 0.0
            XMax = 80.0
            YMin = 0.0
            YMax = 50.0
            ZMin = -3.0
            ZMax = 0.0
            XLength = 80.0
            YLength = 50.0

        class MockShape:
            BoundBox = MockBoundBox()

        class MockFacingOp:
            def __init__(self):
                self.Name = "FacingOp"
                self.Label = "FacingOp"
                self.Shape = MockShape()
                self.Path = Path.Path([Path.Command("G0", {"X": 0.0, "Y": 0.0, "Z": 2.0})])

        facing_op = MockFacingOp()
        main_code, _ = OkumaOSP_post.export([facing_op], filename="-", argstring="--native-cycles")
        self.assertIn("FMILR", main_code)
        self.assertIn("X0.", main_code)
        self.assertIn("Y0.", main_code)
        self.assertIn("Z-3.", main_code)
        self.assertIn("I80.", main_code)
        self.assertIn("J50.", main_code)

    def test_export_drilling_operation_native_bhc(self):
        """Verify CAM Drilling operation with circular holes produces G81 + BHC + G80."""
        class MockDrillingOp:
            def __init__(self):
                self.Name = "DrillingOp"
                self.Label = "DrillingOp"
                cmds = [
                    Path.Command("G81", {"X": 30.0, "Y": 0.0, "Z": -12.0, "R": 2.0, "F": 10.0}),
                    Path.Command("G81", {"X": 0.0, "Y": 30.0, "Z": -12.0, "R": 2.0}),
                    Path.Command("G81", {"X": -30.0, "Y": 0.0, "Z": -12.0, "R": 2.0}),
                    Path.Command("G81", {"X": 0.0, "Y": -30.0, "Z": -12.0, "R": 2.0}),
                ]
                self.Path = Path.Path(cmds)

        drill_op = MockDrillingOp()
        main_code, _ = OkumaOSP_post.export([drill_op], filename="-", argstring="--native-cycles")
        self.assertIn("G81 Z-12. R2. F600.", main_code)
        self.assertIn("BHC X0. Y0. I30. J0. K4 M52", main_code)
        self.assertIn("G80", main_code)

    def test_export_cam_job_multi_tool(self):
        """Verify full CAM Job with multiple operations and tool controllers."""
        class MockToolController:
            def __init__(self, t_num, speed=3000):
                self.ToolNumber = t_num
                self.SpindleSpeed = speed
                self.SpindleDir = "CW"

        class JobProxy:
            Type = "Job"

        class MockJob:
            def __init__(self, ops):
                self.Proxy = JobProxy()
                self.Group = list(ops)

        class MockOp:
            def __init__(self, name, t_num, speed, x, y, z):
                self.Name = name
                self.Label = name
                self.ToolController = MockToolController(t_num, speed=speed)
                self.Path = Path.Path([Path.Command("G1", {"X": x, "Y": y, "Z": z, "F": 10.0})])

        op1 = MockOp("RoughOp", 1, 2500, 10.0, 10.0, -1.0)
        op2 = MockOp("FinishOp", 2, 4000, 20.0, 20.0, -2.0)
        job = MockJob([op1, op2])

        main_code, _ = OkumaOSP_post.export([job], filename="-", argstring="--toolcheck")

        self.assertIn("NAT01", main_code)
        self.assertIn("T1 M6", main_code)
        self.assertIn("G111 T1 Q2", main_code)
        self.assertIn("S2500 M3", main_code)

        self.assertIn("NAT02", main_code)
        self.assertIn("T2 M6", main_code)
        self.assertIn("G111 T2", main_code)
        self.assertIn("S4000 M3", main_code)

    def test_post_parse_function(self):
        """Verify parse() entry point returns optimized G-code string."""
        feat = self.doc.addObject("Path::Feature", "ParseFeat")
        feat.Path = Path.Path([Path.Command("G1", {"X": 5.0, "Y": 10.0, "Z": -0.5, "F": 5.0})])

        output = OkumaOSP_post.parse(feat)
        self.assertTrue(output.startswith("O1000"))
        self.assertIn("X5.", output)
        self.assertIn("Y10.", output)
        self.assertIn("Z-.5", output)
        self.assertIn("M02", output)

    def test_export_cli_flags(self):
        """Verify behavior of various CLI arguments: line-numbers, comments, modal suppression."""
        feat = self.doc.addObject("Path::Feature", "FlagTest")
        feat.Path = Path.Path([
            Path.Command("G1", {"X": 10.0, "Y": 10.0, "Z": -1.0, "F": 10.0}),
            Path.Command("G1", {"X": 20.0, "Y": 10.0, "Z": -1.0, "F": 10.0}),
        ])

        # Test --line-numbers
        gcode_num, _ = OkumaOSP_post.export([feat], filename="-", argstring="--line-numbers")
        self.assertIn("N10", gcode_num)
        self.assertIn("N20", gcode_num)

        # Test --no-comments
        gcode_nocomm, _ = OkumaOSP_post.export([feat], filename="-", argstring="--no-comments --no-header")
        self.assertNotIn("(", gcode_nocomm)

        # Test --no-modal (forces motion code G1 on repeated block)
        gcode_nomodal, _ = OkumaOSP_post.export([feat], filename="-", argstring="--no-modal --no-compress")
        lines = [ln.strip() for ln in gcode_nomodal.splitlines() if "X20." in ln]
        self.assertTrue(any("G1" in ln for ln in lines))



if __name__ == "__main__":
    unittest.main()

