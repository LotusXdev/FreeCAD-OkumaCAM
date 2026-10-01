"""Unit and integration tests for Multi-Program Rough/Finish Export functionality.

Tests compliance with okuma-electric-speeder-supplement-v2.md:
- Generation of separate <Part>_ROUGH.MIN and <Part>_FINISH.MIN files.
- Generation of respective .SUB subprogram files when subprograms are enabled.
- Correct partitioning of roughing vs finishing toolpaths and cycles.
- Combined execution with Electric Spindle Speeder scoped to finish stage.
- Custom rough/finish suffix overrides.
- Backward compatibility of PostResult 2-tuple unpacking.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import Path

try:
    import OkumaOSP_post
    from OkumaOSP_post import PostResult
except ImportError:
    from OkumaCAM import OkumaOSP_post
    from OkumaCAM.OkumaOSP_post import PostResult


class TestSeparateRoughFinish(unittest.TestCase):
    """Test suite for separate roughing and finishing program generation."""

    def setUp(self):
        self.doc = App.newDocument("TestSepDoc")
        self.temp_dir = tempfile.mkdtemp()
        OkumaOSP_post.reset_defaults()

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_mock_job(self):
        """Helper to create a Job with separate RoughOp and FinishOp."""
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
                self.Path = Path.Path([
                    Path.Command("G0", {"X": 0.0, "Y": 0.0, "Z": 10.0}),
                    Path.Command("G1", {"X": x, "Y": y, "Z": z, "F": 10.0}),
                ])

        rough_op = MockOp("RoughOp_Pocket", 1, 2000, 20.0, 20.0, -5.0)
        finish_op = MockOp("FinishOp_Profile", 2, 4500, 25.0, 25.0, -5.0)
        return MockJob([rough_op, finish_op])

    def _create_contour_pocket_op(self):
        """Helper to create a mock OkumaContourPocket object with roughing and finishing tools."""
        class MockToolController:
            def __init__(self, t_num, speed=3000):
                self.ToolNumber = t_num
                self.SpindleSpeed = speed
                self.SpindleDir = "CW"

        class MockOpProxy:
            Type = "OkumaContourPocket"
            residual_commands = []

        class MockContourPocket:
            def __init__(self):
                self.Name = "ContourPocketOp"
                self.Label = "ContourPocketOp"
                self.Proxy = MockOpProxy()
                self.RoughingTool = MockToolController(1, 2500)
                self.FinishingTool = MockToolController(2, 6000)
                self.EnableFinishing = True
                self.StartDepth = 0.0
                self.FinalDepth = -10.0
                self.RoughStepDown = 2.5
                self.FinishStepDown = 1.0
                self.RoughStepOver = 75.0
                self.FinishAllowance = 0.5
                self.InscribedCoreType = "RECTANGLE"
                self.InscribedParams = json.dumps({
                    "xp": 10.0,
                    "yp": 10.0,
                    "idx": 60.0,
                    "jdy": 40.0,
                })
                self.RoughCycle = "Helical / Spiral (PMILR)"
                self.FinishCycle = "Perimeter Only (RMILI)"
                self.UseSpeederForFinishing = False
                self.Path = Path.Path([
                    Path.Command("G0", {"X": 10.0, "Y": 10.0, "Z": 10.0}),
                ])

        return MockContourPocket()

    def test_separate_export_generates_both_files(self):
        """Verify export writes <base>_ROUGH.MIN and <base>_FINISH.MIN."""
        job = self._create_mock_job()
        out_file = os.path.join(self.temp_dir, "MyPart.MIN")

        result = OkumaOSP_post.export(
            [job],
            filename=out_file,
            argstring="--separate-rough-finish",
        )

        rough_file = os.path.join(self.temp_dir, "MyPart_ROUGH.MIN")
        finish_file = os.path.join(self.temp_dir, "MyPart_FINISH.MIN")

        self.assertTrue(os.path.exists(rough_file), "MyPart_ROUGH.MIN should exist")
        self.assertTrue(os.path.exists(finish_file), "MyPart_FINISH.MIN should exist")
        self.assertIn(rough_file, result.files_written)
        self.assertIn(finish_file, result.files_written)

    def test_postresult_unpacking_backward_compatibility(self):
        """Verify PostResult behaves as a 2-tuple (rough_main, finish_main)."""
        job = self._create_mock_job()
        out_file = os.path.join(self.temp_dir, "UnpackPart.MIN")

        res = OkumaOSP_post.export(
            [job],
            filename=out_file,
            argstring="--separate-rough-finish",
        )
        self.assertIsInstance(res, PostResult)
        self.assertIsInstance(res, tuple)

        # Unpack as standard 2-tuple
        r_code, f_code = res
        self.assertEqual(r_code, res.rough_main)
        self.assertEqual(f_code, res.finish_main)
        self.assertIn("O1000", r_code)
        self.assertIn("O1001", f_code)

    def test_roughing_program_content(self):
        """Verify _ROUGH.MIN contains roughing tool and commands, omitting finishing tool."""
        job = self._create_mock_job()
        out_file = os.path.join(self.temp_dir, "ContentTest.MIN")

        result = OkumaOSP_post.export(
            [job],
            filename=out_file,
            argstring="--separate-rough-finish",
        )

        with open(os.path.join(self.temp_dir, "ContentTest_ROUGH.MIN"), "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("( PROGRAM STAGE: ROUGH )", content)
        self.assertIn("T1 M6", content)
        self.assertIn("S2000 M3", content)
        # Finishing tool T2 must not be present
        self.assertNotIn("T2 M6", content)
        self.assertNotIn("S4500", content)
        # Proper end of program
        self.assertIn("M02", content)

    def test_finishing_program_content(self):
        """Verify _FINISH.MIN contains finishing tool and commands, omitting roughing tool."""
        job = self._create_mock_job()
        out_file = os.path.join(self.temp_dir, "ContentTest.MIN")

        result = OkumaOSP_post.export(
            [job],
            filename=out_file,
            argstring="--separate-rough-finish",
        )

        with open(os.path.join(self.temp_dir, "ContentTest_FINISH.MIN"), "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("( PROGRAM STAGE: FINISH )", content)
        self.assertIn("T2 M6", content)
        self.assertIn("S4500 M3", content)
        # Roughing tool T1 must not be present
        self.assertNotIn("T1 M6", content)
        self.assertNotIn("S2000", content)
        # Proper end of program
        self.assertIn("M02", content)

    def test_separate_export_contour_pocket_cycles(self):
        """Verify OkumaContourPocket partitions PMILR into rough and RMILI into finish."""
        pocket = self._create_contour_pocket_op()
        out_file = os.path.join(self.temp_dir, "PocketCycleTest.MIN")

        result = OkumaOSP_post.export(
            [pocket],
            filename=out_file,
            argstring="--separate-rough-finish --native-cycles",
        )

        rough_content = result.rough_main
        finish_content = result.finish_main

        # Roughing program checks
        self.assertIn("PMILR", rough_content)
        self.assertIn("T1 M6", rough_content)
        self.assertNotIn("RMILI", rough_content)
        self.assertNotIn("T2 M6", rough_content)

        # Finishing program checks
        self.assertIn("RMILI", finish_content)
        self.assertIn("T2 M6", finish_content)
        self.assertNotIn("PMILR", finish_content)
        self.assertNotIn("T1 M6", finish_content)

    def test_separate_export_with_speeder_on_finish(self):
        """Verify rough program uses standard spindle while finish program uses electric speeder."""
        pocket = self._create_contour_pocket_op()
        out_file = os.path.join(self.temp_dir, "SpeederSplit.MIN")

        result = OkumaOSP_post.export(
            [pocket],
            filename=out_file,
            argstring="--separate-rough-finish --speeder --speeder-scope=finish",
        )

        rough_content = result.rough_main
        finish_content = result.finish_main

        # Roughing uses standard spindle
        self.assertIn("T1 M6", rough_content)
        self.assertIn("S2500 M3", rough_content)
        self.assertNotIn("M130", rough_content)
        self.assertNotIn("M131", rough_content)

        # Finishing uses electric speeder: M130, M131, M19, dual M00, G94
        self.assertIn("G90 G94", finish_content)
        self.assertIn("M05", finish_content)
        self.assertIn("M19", finish_content)
        self.assertIn("M130", finish_content)
        self.assertIn("G56 H2", finish_content)
        self.assertIn("M131", finish_content)
        self.assertIn("M02", finish_content)

        # Zero main spindle movement in finishing program
        self.assertNotIn("M3", finish_content)
        self.assertNotIn("M03", finish_content)
        self.assertNotIn("M6", finish_content)
        self.assertNotIn("M06", finish_content)
        self.assertNotIn("S6000", finish_content)

    def test_separate_export_with_speeder_on_all(self):
        """Verify both rough and finish programs use electric speeder when scope is all."""
        pocket = self._create_contour_pocket_op()
        out_file = os.path.join(self.temp_dir, "SpeederAll.MIN")

        result = OkumaOSP_post.export(
            [pocket],
            filename=out_file,
            argstring="--separate-rough-finish --speeder --speeder-scope=all",
        )

        for prog_content in (result.rough_main, result.finish_main):
            self.assertIn("M130", prog_content)
            self.assertIn("M131", prog_content)
            self.assertIn("M19", prog_content)
            self.assertNotIn("M03", prog_content)
            self.assertNotIn("M06", prog_content)

    def test_subprograms_partitioned_separate_files(self):
        """Verify roughing and finishing subprograms are written to separate .SUB files."""
        class MockToolController:
            def __init__(self, t_num):
                self.ToolNumber = t_num
                self.SpindleSpeed = 3000
                self.SpindleDir = "CW"

        class MockJobProxy:
            Type = "Job"

        class MockOp:
            def __init__(self, name, t_num):
                self.Name = name
                self.Label = name
                self.ToolController = MockToolController(t_num)
                self.Path = Path.Path([
                    Path.Command("G1", {"X": 0.0, "Y": 0.0, "Z": -1.0, "F": 15.0}),
                    Path.Command("G1", {"X": 20.0, "Y": 0.0}),
                    Path.Command("G1", {"X": 20.0, "Y": 20.0}),
                    Path.Command("G1", {"X": 0.0, "Y": 20.0}),
                    Path.Command("G1", {"X": 0.0, "Y": 0.0}),
                ])

        class MockJob:
            def __init__(self, ops):
                self.Proxy = MockJobProxy()
                self.Group = list(ops)

        job = MockJob([
            MockOp("ContourProfile_Rough", 1),
            MockOp("ContourProfile_Finish", 2),
        ])

        out_file = os.path.join(self.temp_dir, "SubSplit.MIN")
        result = OkumaOSP_post.export(
            [job],
            filename=out_file,
            argstring="--separate-rough-finish --subprograms",
        )

        rough_sub = os.path.join(self.temp_dir, "SubSplit_ROUGH.SUB")
        finish_sub = os.path.join(self.temp_dir, "SubSplit_FINISH.SUB")

        self.assertTrue(os.path.exists(rough_sub), "Rough .SUB file should exist")
        self.assertTrue(os.path.exists(finish_sub), "Finish .SUB file should exist")

        with open(rough_sub, "r", encoding="utf-8") as f:
            r_sub_content = f.read()
        with open(finish_sub, "r", encoding="utf-8") as f:
            f_sub_content = f.read()

        self.assertIn("O0100", r_sub_content)
        self.assertIn("RTS", r_sub_content)
        self.assertIn("CALL O0100", result.rough_main)

        self.assertIn("O0200", f_sub_content)
        self.assertIn("RTS", f_sub_content)
        self.assertIn("CALL O0200", result.finish_main)

    def test_custom_suffixes(self):
        """Verify custom suffixes configured via CLI arguments."""
        job = self._create_mock_job()
        out_file = os.path.join(self.temp_dir, "SuffixPart.MIN")

        result = OkumaOSP_post.export(
            [job],
            filename=out_file,
            argstring="--separate-rough-finish --rough-suffix=_ROUGHING --finish-suffix=_FINISHING",
        )

        custom_rough = os.path.join(self.temp_dir, "SuffixPart_ROUGHING.MIN")
        custom_finish = os.path.join(self.temp_dir, "SuffixPart_FINISHING.MIN")

        self.assertTrue(os.path.exists(custom_rough))
        self.assertTrue(os.path.exists(custom_finish))
        self.assertIn(custom_rough, result.files_written)
        self.assertIn(custom_finish, result.files_written)


if __name__ == "__main__":
    unittest.main()
