"""Unit tests for Okuma G-code low-level compression and numeric formatting."""

from __future__ import annotations

import unittest
from OkumaOptimizer import GCodeCompressor


class TestGCodeCompressor(unittest.TestCase):
    """Test cases for GCodeCompressor methods."""

    def test_abbreviate_code(self):
        """Verify abbreviation of single-digit G, M, T, H, D codes."""
        self.assertEqual(GCodeCompressor.abbreviate_code("G00"), "G0")
        self.assertEqual(GCodeCompressor.abbreviate_code("G01"), "G1")
        self.assertEqual(GCodeCompressor.abbreviate_code("G02"), "G2")
        self.assertEqual(GCodeCompressor.abbreviate_code("G03"), "G3")
        self.assertEqual(GCodeCompressor.abbreviate_code("M03"), "M3")
        self.assertEqual(GCodeCompressor.abbreviate_code("M05"), "M5")
        self.assertEqual(GCodeCompressor.abbreviate_code("M08"), "M8")
        self.assertEqual(GCodeCompressor.abbreviate_code("M09"), "M9")
        self.assertEqual(GCodeCompressor.abbreviate_code("M02"), "M2")
        self.assertEqual(GCodeCompressor.abbreviate_code("T01"), "T1")
        self.assertEqual(GCodeCompressor.abbreviate_code("H01"), "H1")
        self.assertEqual(GCodeCompressor.abbreviate_code("D01"), "D1")
        # Non-abbreviated codes remain unchanged
        self.assertEqual(GCodeCompressor.abbreviate_code("G17"), "G17")
        self.assertEqual(GCodeCompressor.abbreviate_code("G90"), "G90")
        self.assertEqual(GCodeCompressor.abbreviate_code("M30"), "M30")

    def test_format_number_zero_stripping(self):
        """Verify leading, trailing, and sign stripping rules."""
        # Stripping leading zero on decimals
        self.assertEqual(GCodeCompressor.format_number(0.5), ".5")
        self.assertEqual(GCodeCompressor.format_number(-0.75), "-.75")
        self.assertEqual(GCodeCompressor.format_number(0.125), ".125")

        # Stripping trailing zeros
        self.assertEqual(GCodeCompressor.format_number(10.500), "10.5")
        self.assertEqual(GCodeCompressor.format_number(10.0), "10.")
        self.assertEqual(GCodeCompressor.format_number(-5.0), "-5.")

        # Stripping positive signs
        self.assertEqual(GCodeCompressor.format_number(+12.4), "12.4")

        # Zero value
        self.assertEqual(GCodeCompressor.format_number(0.0), "0.")

    def test_compress_line(self):
        """Verify full line compression."""
        line = "G01 X+0.5000 Y-0.7500 Z10.0000 F1200.0"
        compressed = GCodeCompressor.compress_line(line, precision=4, strip_whitespace=True)
        self.assertEqual(compressed, "G1X.5Y-.75Z10.F1200.")

        # Preserving comments
        line_with_comment = "G00 Z5.000 (Safe Rapid)"
        comp_comment = GCodeCompressor.compress_line(line_with_comment, strip_whitespace=True)
        self.assertEqual(comp_comment, "G0Z5. (Safe Rapid)")

    def test_macro_relational_spacing(self):
        """Verify spaces around relational operators inside brackets."""
        raw_macro = "IF[VC1 LE 5]N100"
        formatted = GCodeCompressor.compress_line(raw_macro)
        self.assertIn("[VC1 LE 5]", formatted)

        raw_macro_tight = "IF[VC1LE5]N100"
        formatted_tight = GCodeCompressor.compress_line(raw_macro_tight)
        self.assertIn("[VC1 LE 5]", formatted_tight)

    def test_dense_toolpath_compression_ratio(self):
        """Verify dense toolpath character count reduction exceeds 30% metric benchmark."""
        # Generate 100 dense 3D contour lines with standard FreeCAD G-code formatting
        raw_lines = []
        for i in range(100):
            x = 10.0 + (i * 0.125)
            y = 20.0 - (i * 0.050)
            z = -1.500 - (i * 0.010)
            f = 800.0
            raw_lines.append(f"G01 X+{x:.4f} Y+{y:.4f} Z{z:.4f} F{f:.4f}")

        raw_text = "\n".join(raw_lines)
        raw_size = len(raw_text)

        # Compress all lines
        comp_lines = [
            GCodeCompressor.compress_line(ln, precision=4, strip_whitespace=True)
            for ln in raw_lines
        ]
        comp_text = "\n".join(comp_lines)
        comp_size = len(comp_text)

        reduction_pct = ((raw_size - comp_size) / raw_size) * 100.0
        # Assert at least 30% file size / character reduction as specified in project plan
        self.assertGreater(reduction_pct, 30.0, f"Expected > 30% reduction, got {reduction_pct:.1f}%")

    def test_whitespace_toggle(self):
        """Verify behavior with strip_whitespace=False vs strip_whitespace=True."""
        line = "G01 X+10.500 Y+20.000 F500.0"
        with_spaces = GCodeCompressor.compress_line(line, strip_whitespace=False)
        self.assertEqual(with_spaces, "G1 X10.5 Y20. F500.")

        without_spaces = GCodeCompressor.compress_line(line, strip_whitespace=True)
        self.assertEqual(without_spaces, "G1X10.5Y20.F500.")

    def test_precision_variants(self):
        """Verify formatting with various precision values and keep_decimal_point flag."""
        val = 12.345678
        self.assertEqual(GCodeCompressor.format_number(val, precision=2), "12.35")
        self.assertEqual(GCodeCompressor.format_number(val, precision=5), "12.34568")

        # keep_decimal_point=False
        self.assertEqual(GCodeCompressor.format_number(10.0, keep_decimal_point=False), "10")
        self.assertEqual(GCodeCompressor.format_number(0.0, keep_decimal_point=False), "0")


if __name__ == "__main__":
    unittest.main()

