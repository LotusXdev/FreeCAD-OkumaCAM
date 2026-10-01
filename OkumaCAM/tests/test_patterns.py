"""Unit tests for Okuma coordinate calculation pattern functions (BHC, GRDX, LAA)."""

from __future__ import annotations

import math
import unittest
from OkumaOptimizer import PatternRecognizer


class TestPatternRecognizer(unittest.TestCase):
    """Test cases for hole pattern recognition."""

    def setUp(self):
        self.rec = PatternRecognizer(tolerance=1e-3)

    def test_bolt_hole_circle_4_holes(self):
        """Verify 4-hole circular bolt pattern detection."""
        # 4 holes at radius 25mm centered at (0, 0)
        # Angles: 0, 90, 180, 270 degrees
        holes = [
            (25.0, 0.0),
            (0.0, 25.0),
            (-25.0, 0.0),
            (0.0, -25.0),
        ]
        line = self.rec.recognize_bolt_hole_circle(holes, m52_retract=True)
        self.assertIsNotNone(line)
        self.assertTrue(line.startswith("BHC"))
        self.assertIn("X0.", line)
        self.assertIn("Y0.", line)
        self.assertIn("I25.", line)
        self.assertIn("J0.", line)
        self.assertIn("K4", line)
        self.assertIn("M52", line)

    def test_bolt_hole_circle_6_holes_with_offset(self):
        """Verify 6-hole circle with center offset (50, 30) and start angle 30 deg."""
        cx, cy = 50.0, 30.0
        r = 40.0
        n = 6
        holes = []
        for i in range(n):
            angle = math.radians(30.0 + i * (360.0 / n))
            holes.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

        line = self.rec.recognize_bolt_hole_circle(holes, m52_retract=False)
        self.assertIsNotNone(line)
        self.assertIn("X50.", line)
        self.assertIn("Y30.", line)
        self.assertIn("I40.", line)
        self.assertIn("J30.", line)
        self.assertIn("K6", line)
        self.assertNotIn("M52", line)

    def test_grid_pattern_3x3(self):
        """Verify 3x3 rectangular grid array pattern detection."""
        # dx = 20, dy = 15, nx = 3, ny = 3
        holes = []
        for x in [10.0, 30.0, 50.0]:
            for y in [5.0, 20.0, 35.0]:
                holes.append((x, y))

        line = self.rec.recognize_grid(holes, m52_retract=True)
        self.assertIsNotNone(line)
        self.assertTrue(line.startswith("GRDX") or line.startswith("GRDY"))
        self.assertIn("I20.", line)
        self.assertIn("J15.", line)
        self.assertIn("K3", line)
        self.assertIn("P3", line)
        self.assertIn("M52", line)

    def test_line_at_angle_pattern(self):
        """Verify linear angled hole array (LAA)."""
        # 4 holes at 45 degrees, pitch 10mm
        holes = []
        for i in range(4):
            holes.append((i * 10.0 * math.cos(math.radians(45.0)), i * 10.0 * math.sin(math.radians(45.0))))

        line = self.rec.recognize_line_at_angle(holes, m52_retract=True)
        self.assertIsNotNone(line)
        self.assertTrue(line.startswith("LAA"))
        self.assertIn("I10.", line)
        self.assertIn("K4", line)
        self.assertIn("J45.", line)
        self.assertIn("M52", line)

    def test_irregular_holes_not_recognized(self):
        """Verify non-pattern random hole coordinates return None."""
        random_holes = [(1.2, 3.4), (5.6, 7.8), (12.3, 0.5)]
        self.assertIsNone(self.rec.recognize_bolt_hole_circle(random_holes))
        self.assertIsNone(self.rec.recognize_grid(random_holes))

    def test_bolt_hole_circle_clockwise(self):
        """Verify clockwise stepping emits negative K value."""
        # 4 holes at radius 20mm stepped clockwise: 0 deg, -90 deg, -180 deg, -270 deg
        holes = [
            (20.0, 0.0),
            (0.0, -20.0),
            (-20.0, 0.0),
            (0.0, 20.0),
        ]
        line = self.rec.recognize_bolt_hole_circle(holes, m52_retract=False)
        self.assertIsNotNone(line)
        self.assertTrue(line.startswith("BHC"))
        # Clockwise stepping yields negative K
        self.assertIn("K-4", line)

    def test_insufficient_holes_rejected(self):
        """Verify that hole patterns with fewer than 3 holes return None."""
        one_hole = [(10.0, 10.0)]
        two_holes = [(10.0, 10.0), (20.0, 20.0)]
        self.assertIsNone(self.rec.recognize_bolt_hole_circle(one_hole))
        self.assertIsNone(self.rec.recognize_bolt_hole_circle(two_holes))
        self.assertIsNone(self.rec.recognize_grid(two_holes))
        self.assertIsNone(self.rec.recognize_line_at_angle(two_holes))

    def test_pattern_custom_precision(self):
        """Verify pattern coordinates formatted with custom precision."""
        holes = [
            (25.12345, 0.0),
            (0.0, 25.12345),
            (-25.12345, 0.0),
            (0.0, -25.12345),
        ]
        line = self.rec.recognize_bolt_hole_circle(holes, precision=2)
        self.assertIsNotNone(line)
        self.assertIn("I25.12", line)


if __name__ == "__main__":
    unittest.main()

