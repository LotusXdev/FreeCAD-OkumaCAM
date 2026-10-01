"""Unit and integration tests for Z-slice pattern detection, arbitrary pocket clearing, and drafted wall subprogram loops."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import Path
import OkumaOSP_post
from OkumaOptimizer import (
    GCodeCompressor,
    SliceSimilarityClassifier,
    SubprogramManager,
    ZSlice,
    ZSliceSegmenter,
)


class TestZSliceSubprograms(unittest.TestCase):
    """Test cases for ZSliceSegmenter, SliceSimilarityClassifier, and parametric subprogram generation."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.doc = App.newDocument("TestSliceDoc")

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_pocket_commands(self, depths: list[float], scale_factors: list[float] = None) -> list:
        """Helper to create multi-pass pocket commands."""
        cmds = []
        if scale_factors is None:
            scale_factors = [1.0] * len(depths)

        for z, scale in zip(depths, scale_factors):
            # Rapid to clearance
            cmds.append(Path.Command("G0", {"Z": 2.0}))
            # Rapid to XY start
            cmds.append(Path.Command("G0", {"X": -10.0 * scale, "Y": -10.0 * scale}))
            # Plunge to depth
            cmds.append(Path.Command("G1", {"Z": z, "F": 5.0}))
            # 2D clearing square path
            cmds.append(Path.Command("G1", {"X": 10.0 * scale, "Y": -10.0 * scale, "F": 20.0}))
            cmds.append(Path.Command("G1", {"X": 10.0 * scale, "Y": 10.0 * scale}))
            cmds.append(Path.Command("G1", {"X": -10.0 * scale, "Y": 10.0 * scale}))
            cmds.append(Path.Command("G1", {"X": -10.0 * scale, "Y": -10.0 * scale}))

        return cmds

    def test_zslice_segmentation(self):
        """Verify that multi-depth toolpaths segment into distinct ZSlice objects."""
        depths = [-2.0, -4.0, -6.0, -8.0]
        cmds = self._create_pocket_commands(depths)
        segmenter = ZSliceSegmenter()
        slices = segmenter.segment(cmds)

        self.assertEqual(len(slices), 4)
        for i, s in enumerate(slices):
            self.assertAlmostEqual(s.depth, depths[i], places=3)
            self.assertGreaterEqual(len(s.commands), 4)

    def test_identical_slice_classification(self):
        """Verify that vertical wall identical passes classify as IDENTICAL."""
        depths = [-2.0, -4.0, -6.0, -8.0]
        cmds = self._create_pocket_commands(depths)
        segmenter = ZSliceSegmenter()
        slices = segmenter.segment(cmds)

        classifier = SliceSimilarityClassifier()
        classification, meta = classifier.classify(slices, min_slices=3)

        self.assertEqual(classification, "IDENTICAL")
        self.assertAlmostEqual(meta["stepdown"], 2.0, places=3)
        self.assertAlmostEqual(meta["final_z"], -8.0, places=3)
        self.assertEqual(meta["slice_count"], 4)

    def test_drafted_slice_classification(self):
        """Verify that concentric contracting passes classify as DRAFTED_SCALED."""
        depths = [-2.0, -4.0, -6.0, -8.0]
        # Scales contracting by 5% per 2mm pass -> 20mm span * 0.05 = 1mm total = 0.5mm per side -> atan(0.5/2) = ~14 deg
        scales = [1.0, 0.95, 0.90, 0.85]
        cmds = self._create_pocket_commands(depths, scale_factors=scales)
        segmenter = ZSliceSegmenter()
        slices = segmenter.segment(cmds)

        classifier = SliceSimilarityClassifier()
        classification, meta = classifier.classify(slices, min_slices=3)

        self.assertEqual(classification, "DRAFTED_SCALED")
        self.assertAlmostEqual(meta["scale_start"], 1.0, places=3)
        self.assertAlmostEqual(meta["scale_step"], 0.05, places=3)
        self.assertGreater(meta["draft_angle"], 0.0)

    def test_local_var_loop_generation(self):
        """Verify that local variable loop emits LA, LB, LC without VC common variables."""
        loop = SubprogramManager.generate_parametric_loop(
            sub_id=200,
            start_z=0.0,
            final_z=-10.0,
            stepdown=2.0,
            plunge_clearance=2.0,
            draft_mode="none",
            var_scope="local",
        )
        text = "\n".join(loop)

        # Local variables
        self.assertIn("LA=-2.", text)
        self.assertIn("LB=2.", text)
        self.assertIn("LC=-10.", text)
        self.assertIn("CALL O0200 PZ=[LA] PR=2.", text)
        self.assertIn("LA=LA-LB", text)
        self.assertIn("IF [LA GE LC] N100", text)
        # Ensure NO global VC common variables are used
        self.assertNotIn("VC", text)

    def test_g51_scaling_draft_loop(self):
        """Verify that G51 coordinate scaling wraps the CALL and cancels with G50."""
        loop = SubprogramManager.generate_parametric_loop(
            sub_id=210,
            start_z=0.0,
            final_z=-8.0,
            stepdown=2.0,
            plunge_clearance=2.0,
            draft_mode="scale",
            centroid=(25.0, 15.0),
            scale_start=1.0,
            scale_step=0.05,
            var_scope="local",
        )
        text = "\n".join(loop)

        self.assertIn("G51 X25. Y15. P[LD]", text)
        self.assertIn("CALL O0210 PZ=[LA] PR=2.", text)
        self.assertIn("G50", text)
        self.assertIn("LD=LD-LE", text)

    def test_offset_draft_loop(self):
        """Verify tool offset / PR argument passing when draft_mode is offset."""
        loop = SubprogramManager.generate_parametric_loop(
            sub_id=220,
            start_z=0.0,
            final_z=-6.0,
            stepdown=2.0,
            draft_mode="offset",
            offset_start=0.0,
            offset_step=0.176,
            var_scope="local",
        )
        text = "\n".join(loop)

        self.assertIn("CALL O0220 PZ=[LA] PR=2. PD=[LD]", text)
        self.assertIn("LD=LD+LE", text)

    def test_threshold_shallow_pocket_remains_inline(self):
        """Verify that a 2-pass shallow pocket remains inlined when threshold is 3."""
        depths = [-2.0, -4.0]
        cmds = self._create_pocket_commands(depths)
        feat = self.doc.addObject("Path::Feature", "ShallowPocket")
        feat.Path = Path.Path(cmds)

        out_min = os.path.join(self.temp_dir, "Shallow.MIN")
        main_code, sub_code = OkumaOSP_post.export(
            [feat], filename=out_min, argstring="--min-slices=3 --no-toolcheck"
        )

        # Should not generate a CALL loop because it had only 2 slices (< 3)
        self.assertNotIn("CALL O0100", main_code)
        self.assertIsNone(sub_code)

    def test_end_to_end_pocket_subprogram_export(self):
        """Verify full export of a 4-pass pocket into .MIN (LA loop) and .SUB (PZ/PR subprogram)."""
        depths = [-2.0, -4.0, -6.0, -8.0]
        cmds = self._create_pocket_commands(depths)
        feat = self.doc.addObject("Path::Feature", "DeepPocket")
        feat.Path = Path.Path(cmds)

        out_min = os.path.join(self.temp_dir, "DeepPocket.MIN")
        main_code, sub_code = OkumaOSP_post.export(
            [feat], filename=out_min, argstring="--min-slices=3 --no-toolcheck"
        )

        # Verify main program contains local variable loop calling O0100
        self.assertIn("LA=-2.", main_code)
        self.assertIn("LB=2.", main_code)
        self.assertIn("LC=-8.", main_code)
        self.assertIn("CALL O0100 PZ=[LA] PR=2.", main_code)
        self.assertIn("IF [LA GE LC] N100", main_code)


        # Verify subprogram content
        out_sub = os.path.join(self.temp_dir, "DeepPocket.SUB")
        self.assertTrue(os.path.exists(out_sub))
        with open(out_sub, "r", encoding="utf-8") as f:
            sub_content = f.read()

        self.assertIn("O0100", sub_content)
        self.assertIn("G0 Z[PZ+PR]", sub_content)
        self.assertIn("G1 Z[PZ]", sub_content)
        self.assertTrue(sub_content.strip().endswith("RTS"))


if __name__ == "__main__":
    unittest.main()
