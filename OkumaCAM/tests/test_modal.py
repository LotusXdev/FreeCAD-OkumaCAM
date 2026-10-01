"""Unit tests for modal state tracking and axis/motion suppression."""

from __future__ import annotations

import unittest
from OkumaOptimizer import ModalTracker, OkumaOptimizer


class TestModalTracker(unittest.TestCase):
    """Test cases for ModalTracker and OkumaOptimizer block optimization."""

    def setUp(self):
        self.modal = ModalTracker(tolerance=1e-4)

    def test_motion_suppression(self):
        """Verify repeated motion code is suppressed."""
        # First motion G1 is emitted
        m1, ax1, f1, s1 = self.modal.filter_command("G1", {"X": 10.0, "Y": 20.0}, feedrate=500.0)
        self.assertEqual(m1, "G1")
        self.assertEqual(ax1, {"X": 10.0, "Y": 20.0})
        self.assertEqual(f1, 500.0)

        # Second motion G1 is suppressed
        m2, ax2, f2, s2 = self.modal.filter_command("G1", {"X": 30.0, "Y": 20.0}, feedrate=500.0)
        self.assertIsNone(m2)
        # Y is unchanged, so only X should be emitted
        self.assertEqual(ax2, {"X": 30.0})
        # F is unchanged, so feedrate should be suppressed
        self.assertIsNone(f2)

    def test_motion_mode_switch(self):
        """Verify switching from G1 to G0 emits new mode."""
        self.modal.filter_command("G1", {"X": 10.0})
        m, ax, _, _ = self.modal.filter_command("G0", {"Z": 5.0})
        self.assertEqual(m, "G0")
        self.assertEqual(ax, {"Z": 5.0})

    def test_arc_parameters_not_suppressed(self):
        """Verify arc parameters (I, J, K) are emitted every block."""
        m1, ax1, _, _ = self.modal.filter_command("G2", {"X": 20.0, "Y": 0.0, "I": 10.0, "J": 0.0})
        self.assertEqual(ax1.get("I"), 10.0)
        self.assertEqual(ax1.get("J"), 0.0)

        # Even if I and J have same values on next arc block, they must not be suppressed
        m2, ax2, _, _ = self.modal.filter_command("G2", {"X": 40.0, "Y": 0.0, "I": 10.0, "J": 0.0})
        self.assertIn("I", ax2)
        self.assertIn("J", ax2)

    def test_optimizer_block_emission(self):
        """Verify full optimized block strings."""
        opt = OkumaOptimizer(precision=4, strip_whitespace=False, enable_modal=True)
        block1 = opt.optimize_block("G1", {"X": 10.0, "Y": 20.0, "Z": -1.0}, feedrate=1200.0)
        self.assertEqual(block1, "G1 X10. Y20. Z-1. F1200.")

        # Next block at same Z and F
        block2 = opt.optimize_block("G1", {"X": 30.0, "Y": 20.0, "Z": -1.0}, feedrate=1200.0)
        self.assertEqual(block2, "X30.")


if __name__ == "__main__":
    unittest.main()
