"""Unit and integration tests for Electric Spindle Speeder functionality.

Tests compliance with okuma-electric-speeder-supplement-v2.md:
- Dual M00 stops & M19 orientation lock.
- M130 interlock bypass & M131 restoration.
- G94 feed-per-minute enforcement.
- Zero main spindle movement assertion (M03, M04, S > 0, M06, G111).
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import Path

try:
    import OkumaOSP_post
    from OkumaOSP_post import (
        SpeederPostError,
        process_speeder_cleanup,
        process_speeder_header,
        verify_no_spindle_movement_after_speeder_load,
    )
except ImportError:
    from OkumaCAM import OkumaOSP_post
    from OkumaCAM.OkumaOSP_post import (
        SpeederPostError,
        process_speeder_cleanup,
        process_speeder_header,
        verify_no_spindle_movement_after_speeder_load,
    )


class TestElectricSpeeder(unittest.TestCase):
    """Test suite for electric spindle speeder post-processing and safety rules."""

    def setUp(self):
        self.doc = App.newDocument("TestSpeederDoc")
        self.temp_dir = tempfile.mkdtemp()
        OkumaOSP_post.reset_defaults()

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_speeder_header_generation_dual_m00(self):
        """Verify speeder header generation with dual M00 stops."""
        lines = process_speeder_header(dual_m00=True)
        header_text = "\n".join(lines)

        self.assertIn("G90 G94", header_text)
        self.assertIn("M05", header_text)
        self.assertIn("M19", header_text)
        self.assertIn("M130", header_text)
        # Should contain two M00 stops
        m00_occurrences = [line for line in lines if line.strip() == "M00"]
        self.assertEqual(len(m00_occurrences), 2)

    def test_speeder_header_generation_single_m00(self):
        """Verify speeder header generation with single M00 stop."""
        lines = process_speeder_header(dual_m00=False)
        m00_occurrences = [line for line in lines if line.strip() == "M00"]
        self.assertEqual(len(m00_occurrences), 1)
        header_text = "\n".join(lines)
        self.assertIn("M19", header_text)
        self.assertIn("M130", header_text)

    def test_speeder_cleanup_generation(self):
        """Verify speeder cleanup restores M131 and commands final M00 unloading stop."""
        lines = process_speeder_cleanup(retract_z=200.0, precision=4)
        cleanup_text = "\n".join(lines)

        self.assertIn("G00 Z200.", cleanup_text)
        self.assertIn("M131", cleanup_text)
        self.assertIn("M00", cleanup_text)
        self.assertIn("M02", cleanup_text)

    def test_verification_success_clean_toolpath(self):
        """Verify safety assertion succeeds when no spindle rotation is present."""
        gcode = [
            "O1000",
            "G90 G94",
            "M05",
            "M00",
            "M19",
            "M00",
            "M130",
            "G15 H1",
            "G56 H1",
            "G0 X0. Y0. Z50.",
            "G1 Z-2. F1000.",
            "X50. Y50.",
            "G0 Z50.",
            "M131",
            "M00",
            "M02",
        ]
        self.assertTrue(verify_no_spindle_movement_after_speeder_load(gcode, dual_m00=True))

    def test_verification_fails_on_m03(self):
        """Verify safety assertion raises SpeederPostError on M03 after speeder load."""
        gcode = [
            "O1000",
            "M00",
            "M19",
            "M00",
            "M130",
            "M03 S1000",
            "G1 X10. F500.",
        ]
        with self.assertRaises(SpeederPostError) as ctx:
            verify_no_spindle_movement_after_speeder_load(gcode, dual_m00=True)
        self.assertIn("Spindle start command detected", str(ctx.exception))

    def test_verification_fails_on_m04(self):
        """Verify safety assertion raises SpeederPostError on M04 after speeder load."""
        gcode = [
            "O1000",
            "M00",
            "M19",
            "M00",
            "M130",
            "M4",
            "G1 X10. F500.",
        ]
        with self.assertRaises(SpeederPostError) as ctx:
            verify_no_spindle_movement_after_speeder_load(gcode, dual_m00=True)
        self.assertIn("Spindle start command detected", str(ctx.exception))

    def test_verification_fails_on_spindle_rpm(self):
        """Verify safety assertion raises SpeederPostError on S > 0 after speeder load."""
        gcode = [
            "O1000",
            "M00",
            "M19",
            "M00",
            "M130",
            "S24000",
            "G1 X10. F500.",
        ]
        with self.assertRaises(SpeederPostError) as ctx:
            verify_no_spindle_movement_after_speeder_load(gcode, dual_m00=True)
        self.assertIn("Spindle speed S > 0 detected", str(ctx.exception))

    def test_verification_fails_on_tool_change_m06(self):
        """Verify safety assertion raises SpeederPostError on M06 after speeder load."""
        gcode = [
            "O1000",
            "M00",
            "M19",
            "M00",
            "M130",
            "T2 M06",
        ]
        with self.assertRaises(SpeederPostError) as ctx:
            verify_no_spindle_movement_after_speeder_load(gcode, dual_m00=True)
        self.assertIn("Automatic tool change detected", str(ctx.exception))

    def test_verification_fails_on_g111(self):
        """Verify safety assertion raises SpeederPostError on G111 ATC macro after speeder load."""
        gcode = [
            "O1000",
            "M00",
            "M19",
            "M00",
            "M130",
            "G111 T2",
        ]
        with self.assertRaises(SpeederPostError) as ctx:
            verify_no_spindle_movement_after_speeder_load(gcode, dual_m00=True)
        self.assertIn("Automatic tool change detected", str(ctx.exception))

    def test_verification_fails_on_g95(self):
        """Verify safety assertion raises SpeederPostError on G95 feed per revolution."""
        gcode = [
            "O1000",
            "M00",
            "M19",
            "M00",
            "M130",
            "G95 F0.1",
        ]
        with self.assertRaises(SpeederPostError) as ctx:
            verify_no_spindle_movement_after_speeder_load(gcode, dual_m00=True)
        self.assertIn("Feed-per-revolution G95 detected", str(ctx.exception))

    def test_end_to_end_speeder_export_all_operations(self):
        """Verify full export of a toolpath under --speeder produces complete setup & cleanup."""
        feat = self.doc.addObject("Path::Feature", "SpeederCut")
        cmd_cut = Path.Command("G1", {"X": 25.0, "Y": 25.0, "Z": -1.0, "F": 16.66})  # 1000 mm/min
        feat.Path = Path.Path([cmd_cut])

        out_min = os.path.join(self.temp_dir, "SpeederJob.MIN")
        result = OkumaOSP_post.export(
            [feat],
            filename=out_min,
            argstring="--speeder --speeder-scope=all --speeder-retract=250.0",
        )
        content = result.main_code

        # Verify header
        self.assertIn("G90 G94", content)
        self.assertIn("M05", content)
        self.assertIn("M19", content)
        self.assertIn("M130", content)

        # Verify no M3, M4, S, M6
        self.assertNotIn("M3", content)
        self.assertNotIn("M03", content)
        self.assertNotIn("M4", content)
        self.assertNotIn("M04", content)
        self.assertNotIn("M6", content)
        self.assertNotIn("M06", content)

        # Verify cleanup
        self.assertIn("G00 Z250.", content)
        self.assertIn("M131", content)
        self.assertIn("M00", content)
        self.assertIn("M02", content)


if __name__ == "__main__":
    unittest.main()
