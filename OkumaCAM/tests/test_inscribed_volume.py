"""Unit tests for OkumaCAM InscribedVolumeAnalyzer."""

from __future__ import annotations

import math
import unittest

try:
    from OkumaCAM.InscribedVolume import (
        InscribedCircle,
        InscribedRectangle,
        InscribedResult,
        InscribedVolumeAnalyzer,
    )
except ImportError:
    from InscribedVolume import (
        InscribedCircle,
        InscribedRectangle,
        InscribedResult,
        InscribedVolumeAnalyzer,
    )


class TestInscribedVolume(unittest.TestCase):
    """Test suite for InscribedVolumeAnalyzer algorithms."""

    def test_shoelace_polygon_area(self):
        """Verify Shoelace polygon area calculation."""
        # 100 x 50 rectangle
        rect = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)]
        area = InscribedVolumeAnalyzer.polygon_area(rect)
        self.assertAlmostEqual(abs(area), 5000.0, places=3)

        # Triangle
        tri = [(0.0, 0.0), (40.0, 0.0), (0.0, 30.0)]
        area_tri = InscribedVolumeAnalyzer.polygon_area(tri)
        self.assertAlmostEqual(abs(area_tri), 600.0, places=3)

    def test_point_in_polygon(self):
        """Verify ray-casting point-in-polygon containment."""
        poly = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
        self.assertTrue(InscribedVolumeAnalyzer.point_in_polygon(50.0, 50.0, poly))
        self.assertFalse(InscribedVolumeAnalyzer.point_in_polygon(150.0, 50.0, poly))
        self.assertFalse(InscribedVolumeAnalyzer.point_in_polygon(-10.0, 50.0, poly))

        # Test hole exclusion
        hole = [(40.0, 40.0), (60.0, 40.0), (60.0, 60.0), (40.0, 60.0)]
        self.assertFalse(InscribedVolumeAnalyzer.point_in_polygon(50.0, 50.0, poly, holes=[hole]))
        self.assertTrue(InscribedVolumeAnalyzer.point_in_polygon(20.0, 20.0, poly, holes=[hole]))

    def test_largest_inscribed_circle_on_round_boundary(self):
        """Verify Pole of Inaccessibility converges on center and radius of a circle."""
        r_expected = 40.0
        n_pts = 36
        poly = [
            (50.0 + r_expected * math.cos(i * 2.0 * math.pi / n_pts),
             50.0 + r_expected * math.sin(i * 2.0 * math.pi / n_pts))
            for i in range(n_pts)
        ]

        circ = InscribedVolumeAnalyzer.find_largest_inscribed_circle(poly, tolerance=0.1)
        self.assertAlmostEqual(circ.center_x, 50.0, delta=0.5)
        self.assertAlmostEqual(circ.center_y, 50.0, delta=0.5)
        self.assertAlmostEqual(circ.radius, r_expected, delta=0.5)
        self.assertAlmostEqual(circ.area, math.pi * r_expected * r_expected, delta=150.0)

    def test_largest_inscribed_circle_on_rectangle(self):
        """For a 100x60 rectangle, largest inscribed circle radius should be 30."""
        poly = [(0.0, 0.0), (100.0, 0.0), (100.0, 60.0), (0.0, 60.0)]
        circ = InscribedVolumeAnalyzer.find_largest_inscribed_circle(poly, tolerance=0.1)
        self.assertAlmostEqual(circ.radius, 30.0, delta=0.5)
        self.assertAlmostEqual(circ.center_y, 30.0, delta=0.5)

    def test_maximum_inscribed_rectangle_on_rectangle(self):
        """Verify MIR algorithm recovers full area on axis-aligned rectangle."""
        poly = [(10.0, 10.0), (110.0, 10.0), (110.0, 60.0), (10.0, 60.0)]
        rec = InscribedVolumeAnalyzer.find_maximum_inscribed_rectangle(poly, grid_resolution=1.0)
        self.assertAlmostEqual(rec.width, 100.0, delta=2.0)
        self.assertAlmostEqual(rec.height, 50.0, delta=2.0)
        self.assertAlmostEqual(rec.area, 5000.0, delta=200.0)

    def test_maximum_inscribed_rectangle_on_l_shape(self):
        """Verify MIR algorithm identifies large core on an L-shaped pocket."""
        # L-shape: 100x100 minus top-right 50x50 block
        # Total area = 7500. Expected core rectangle = 100x50 or 50x100 (area = 5000)
        poly = [
            (0.0, 0.0),
            (100.0, 0.0),
            (100.0, 50.0),
            (50.0, 50.0),
            (50.0, 100.0),
            (0.0, 100.0),
        ]
        res = InscribedVolumeAnalyzer.analyze_pocket(poly, tool_diameter=10.0, min_coverage=0.40)
        self.assertEqual(res.strategy, "RECTANGLE")
        self.assertIsNotNone(res.rectangle)
        self.assertAlmostEqual(res.coverage_ratio, 5000.0 / 7500.0, delta=0.05)
        self.assertTrue(res.rectangle.width >= 48.0)
        self.assertTrue(res.rectangle.height >= 48.0)

    def test_circular_pocket_selection(self):
        """Verify circular boundary prioritizes CIRCLE over RECTANGLE."""
        n_pts = 32
        poly = [
            (40.0 * math.cos(i * 2.0 * math.pi / n_pts),
             40.0 * math.sin(i * 2.0 * math.pi / n_pts))
            for i in range(n_pts)
        ]
        res = InscribedVolumeAnalyzer.analyze_pocket(poly, tool_diameter=10.0, min_coverage=0.40)
        self.assertEqual(res.strategy, "CIRCLE")
        self.assertIsNotNone(res.circle)
        self.assertTrue(res.coverage_ratio > 0.90)

    def test_low_coverage_fallback_to_none(self):
        """Verify irregular / narrow pocket with poor inscribed coverage returns NONE."""
        # Long narrow cross: center 12x12 with 4 narrow 5x40 arms
        # Roughing tool diameter 10mm cannot fit large rectangle or circle in arms
        poly = [
            (0.0, 20.0), (30.0, 20.0), (30.0, 0.0), (42.0, 0.0),
            (42.0, 20.0), (72.0, 20.0), (72.0, 32.0), (42.0, 32.0),
            (42.0, 52.0), (30.0, 52.0), (30.0, 32.0), (0.0, 32.0),
        ]
        res = InscribedVolumeAnalyzer.analyze_pocket(
            poly, tool_diameter=10.0, min_coverage=0.75
        )
        self.assertEqual(res.strategy, "NONE")

    def test_residual_clearing_commands(self):
        """Verify residual toolpath generation produces valid G0/G1 moves."""
        residual_poly = [(0.0, 50.0), (50.0, 50.0), (50.0, 100.0), (0.0, 100.0)]
        cmds = InscribedVolumeAnalyzer.generate_residual_clearing_commands(
            residual_polygons=[residual_poly],
            tool_diameter=10.0,
            stepover_ratio=0.7,
            feedrate=300.0,
        )
        self.assertTrue(len(cmds) > 0)
        g1_moves = [c for c in cmds if c[0] == "G1"]
        self.assertTrue(len(g1_moves) > 0)
        # Check feedrate parameter present
        self.assertIn("F", g1_moves[0][1])
        self.assertEqual(g1_moves[0][1]["F"], 300.0)


if __name__ == "__main__":
    unittest.main()
