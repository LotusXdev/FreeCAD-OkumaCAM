"""Unit tests for Okuma native area machining cycles (FMILR/FMILF, PMIL/PMILR, RMILO/RMILI) and subprograms."""

from __future__ import annotations

import unittest
from OkumaOptimizer import AreaMachiningEngine, SubprogramManager


class TestAreaMachining(unittest.TestCase):
    """Test cases for area machining command generation and subprogram handling."""

    def test_fmilr_face_milling_roughing(self):
        """Verify FMILR roughing command parameter construction."""
        cmd = AreaMachiningEngine.generate_command(
            mnemonic="FMILR",
            xp=0.0,
            yp=0.0,
            zp=-2.5,
            idx=100.0,
            jdy=60.0,
            q_stepdown=1.25,
            r_rapid_level=2.0,
            k_allowance=0.2,
            p_stepover_ratio=70.0,
            d_offset_num=1,
            feedrate=300.0,
            precision=4,
        )
        self.assertTrue(cmd.startswith("FMILR"))
        self.assertIn("X0.", cmd)
        self.assertIn("Y0.", cmd)
        self.assertIn("Z-2.5", cmd)
        self.assertIn("I100.", cmd)
        self.assertIn("J60.", cmd)
        self.assertIn("K.2", cmd)
        self.assertIn("P70", cmd)
        self.assertIn("Q1.25", cmd)
        self.assertIn("R2.", cmd)
        self.assertIn("D1", cmd)
        self.assertIn("F300.", cmd)
        # Default FA is 4 * F (1200), FB is F / 4 (75)
        self.assertIn("FA=1200.", cmd)
        self.assertIn("FB=75.", cmd)

    def test_fmilf_face_milling_finishing(self):
        """Verify FMILF finishing command."""
        cmd = AreaMachiningEngine.generate_command(
            mnemonic="FMILF",
            xp=10.0,
            yp=10.0,
            zp=-1.0,
            idx=50.0,
            jdy=30.0,
            feedrate=200.0,
        )
        self.assertTrue(cmd.startswith("FMILF"))
        self.assertIn("X10.", cmd)
        self.assertIn("Y10.", cmd)
        self.assertIn("Z-1.", cmd)

    def test_pmil_pocket_milling(self):
        """Verify PMIL and PMILR pocket milling commands."""
        pmil = AreaMachiningEngine.generate_command(
            mnemonic="PMIL",
            xp=0.0,
            yp=0.0,
            zp=-10.0,
            idx=40.0,
            jdy=40.0,
            q_stepdown=2.0,
            feedrate=250.0,
        )
        self.assertTrue(pmil.startswith("PMIL"))
        self.assertIn("Z-10.", pmil)
        self.assertIn("Q2.", pmil)

        pmilr = AreaMachiningEngine.generate_command(
            mnemonic="PMILR",
            xp=0.0,
            yp=0.0,
            zp=-10.0,
            idx=40.0,
            jdy=40.0,
            feedrate=250.0,
        )
        self.assertTrue(pmilr.startswith("PMILR"))

    def test_rmilo_perimeter_milling(self):
        """Verify RMILO outer perimeter milling command."""
        rmilo = AreaMachiningEngine.generate_command(
            mnemonic="RMILO",
            xp=5.0,
            yp=5.0,
            zp=-5.0,
            idx=80.0,
            jdy=50.0,
            feedrate=350.0,
        )
        self.assertTrue(rmilo.startswith("RMILO"))

    def test_rmili_internal_perimeter_milling(self):
        """Verify RMILI internal perimeter milling command."""
        rmili = AreaMachiningEngine.generate_command(
            mnemonic="RMILI",
            xp=2.0,
            yp=2.0,
            zp=-4.0,
            idx=40.0,
            jdy=30.0,
            feedrate=280.0,
            d_offset_num=2,
            p_stepover_ratio=65.0,
        )
        self.assertTrue(rmili.startswith("RMILI"))
        self.assertIn("X2.", rmili)
        self.assertIn("Y2.", rmili)
        self.assertIn("Z-4.", rmili)
        self.assertIn("I40.", rmili)
        self.assertIn("J30.", rmili)
        self.assertIn("D2", rmili)
        self.assertIn("P65", rmili)
        self.assertIn("F280.", rmili)

    def test_area_machining_stepover_and_feed_parameters(self):
        """Verify stepover ratio variations and custom FA/FB calculations."""
        cmd = AreaMachiningEngine.generate_command(
            mnemonic="FMILR",
            xp=0.0,
            yp=0.0,
            zp=-5.0,
            idx=50.0,
            jdy=50.0,
            feedrate=400.0,
            p_stepover_ratio=50.0,
            fa_transition_feed=1200.0,
            fb_infeed_feed=200.0,
        )
        self.assertIn("P50", cmd)
        self.assertIn("FA=1200.", cmd)
        self.assertIn("FB=200.", cmd)



    def test_subprogram_generation(self):
        """Verify .SUB subprogram generation ending with RTS."""
        mgr = SubprogramManager(start_sub_id=100)
        lines = ["G1 X10. Y0.", "G1 X10. Y10.", "G1 X0. Y10.", "G1 X0. Y0."]
        sub_id = mgr.create_subprogram(lines)
        self.assertEqual(sub_id, 100)

        sub_content = mgr.generate_sub_file_content(sub_id)
        self.assertTrue(sub_content.startswith("O0100"))
        self.assertIn("G1 X10. Y0.", sub_content)
        self.assertTrue(sub_content.strip().endswith("RTS"))

    def test_subprogram_call_loop(self):
        """Verify User Task macro loop in main program."""
        mgr = SubprogramManager()
        loop_lines = mgr.generate_call_loop(
            sub_id=100,
            start_z=0.0,
            final_z=-6.0,
            stepdown=2.0,
            feedrate=150.0,
            var_num=1,
        )
        joined = "\n".join(loop_lines)
        self.assertIn("VC1=-2.", joined)
        self.assertIn("CALL O0100", joined)
        self.assertIn("IF [VC1 GE -6.] N100", joined)


if __name__ == "__main__":
    unittest.main()

