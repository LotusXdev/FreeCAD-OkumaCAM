"""Okuma OSP CAM Optimizer and Code Generation Engine.

This module provides high-efficiency G-code compression, modal state tracking,
native Okuma area machining cycles (FMILR/FMILF, PMIL/PMILR, RMILO/RMILI),
hole pattern recognition (BHC, ARC, GRDX, GRDY, LAA), and subprogram extraction
specifically optimized for Okuma OSP CNC controls (OSP7000, OSP-P series).

Note on User Macro G111:
    G111 is strictly reserved for the Okuma OTCHK subprogram in TOOLCHK.LIB
    (tool break/pre-check detection) and is never repurposed for user macros.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

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


class GCodeCompressor:
    """Provides low-level G-code character compression and numeric optimization.

    Compresses numeric representations, strips redundant leading/trailing zeros,
    abbreviates single-digit G/M codes, and minimizes line whitespace.
    """

    # Matches addresses with values, e.g. G01, X-0.500, FA=1200.0, etc.
    RE_TOKEN = re.compile(r"([A-Za-z]+(?:=)?)\s*([+-]?[0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?)")

    @staticmethod
    def abbreviate_code(code_str: str) -> str:
        """Abbreviate G/M/T/H/D double-digit codes (e.g. G00 -> G0, M03 -> M3).

        Args:
            code_str: The raw code token (e.g. 'G01', 'M08', 'T01').

        Returns:
            Compressed token (e.g. 'G1', 'M8', 'T1').
        """
        if not code_str:
            return ""
        letter = code_str[0].upper()
        if letter in ("G", "M", "T", "H", "D") and len(code_str) > 1:
            val_part = code_str[1:]
            if val_part.isdigit():
                return f"{letter}{int(val_part)}"
        return code_str

    @staticmethod
    def format_number(
        val: Union[float, int],
        precision: int = 4,
        strip_leading_zero: bool = True,
        strip_trailing_zero: bool = True,
        keep_decimal_point: bool = True,
    ) -> str:
        """Format a numeric coordinate or feedrate with Okuma zero-stripping rules.

        Examples:
            0.5   -> ".5"
            -0.75 -> "-.75"
            10.500-> "10.5"
            10.0  -> "10."
            +12.4 -> "12.4"
            0.0   -> "0." or "0"

        Args:
            val: Numeric value.
            precision: Maximum decimal places.
            strip_leading_zero: Whether to strip leading zero before decimal point.
            strip_trailing_zero: Whether to strip trailing zeros after decimal point.
            keep_decimal_point: Whether to retain decimal point if all fractional digits are stripped.

        Returns:
            Compact numeric string.
        """
        if isinstance(val, int):
            return f"{val}." if keep_decimal_point else str(val)

        # Round to given precision
        rounded = round(float(val), precision)
        # Avoid -0.0
        if abs(rounded) < 1e-12:
            return "0." if keep_decimal_point else "0"

        formatted = f"{rounded:.{precision}f}"

        if "." in formatted:
            if strip_trailing_zero:
                formatted = formatted.rstrip("0")
                if formatted.endswith("."):
                    if not keep_decimal_point:
                        formatted = formatted[:-1]

            if strip_leading_zero:
                if formatted.startswith("0."):
                    formatted = formatted[1:]
                elif formatted.startswith("-0."):
                    formatted = "-" + formatted[2:]
                elif formatted.startswith("+0."):
                    formatted = formatted[2:]

        if formatted.startswith("+"):
            formatted = formatted[1:]

        return formatted

    @classmethod
    def compress_line(
        cls,
        line: str,
        precision: int = 4,
        strip_whitespace: bool = True,
        strip_comments: bool = False,
    ) -> str:
        """Compress a single G-code line according to Okuma rules.

        Args:
            line: Raw G-code line.
            precision: Decimal precision for coordinates.
            strip_whitespace: Strip whitespace between address letters and values.
            strip_comments: Strip parentheses and comments if True.

        Returns:
            Optimized, compressed line.
        """
        line = line.strip()
        if not line:
            return ""

        # Separate line comments (parenthetical or semicolon)
        comment = ""
        code_part = line
        if "(" in line:
            c_start = line.find("(")
            c_end = line.find(")", c_start)
            if c_end != -1:
                comment = line[c_start : c_end + 1]
                code_part = line[:c_start] + line[c_end + 1 :]
            else:
                comment = line[c_start:]
                code_part = line[:c_start]
        elif ";" in line:
            c_start = line.find(";")
            comment = line[c_start:]
            code_part = line[:c_start]

        code_part = code_part.strip()
        if not code_part:
            return "" if strip_comments else comment

        tokens = []
        # Check for branching statement (e.g. IF [VC1 LE 5] N100) or CALL / MODIN / cycles
        code_upper = code_part.upper()
        if code_upper.startswith("IF") or any(kw in code_upper for kw in ("CALL ", "MODIN", "MODOUT", "BHC ", "ARC ", "GRDX ", "GRDY ", "LAA ", "FMIL", "PMIL", "RMIL")):
            # Macro / cycle line: preserve required keyword spacing
            tokens.append(cls._format_macro_line(code_part, precision))
        else:
            # Standard G-code line
            parts = code_part.split()
            for p in parts:
                match = cls.RE_TOKEN.match(p)
                if match:
                    addr, num_str = match.groups()
                    addr_upper = addr.upper()
                    if addr_upper in ("G", "M", "T", "H", "D") and not addr.endswith("="):
                        tokens.append(cls.abbreviate_code(f"{addr_upper}{num_str}"))
                    elif addr_upper == "N":
                        # Block number
                        tokens.append(f"N{int(float(num_str))}")
                    else:
                        num_val = float(num_str)
                        formatted_val = cls.format_number(num_val, precision=precision)
                        tokens.append(f"{addr}{formatted_val}")
                else:
                    tokens.append(p)

        join_char = "" if strip_whitespace else " "
        compressed = join_char.join(tokens)

        if comment and not strip_comments:
            compressed = f"{compressed} {comment}".strip()

        return compressed

    @classmethod
    def _format_macro_line(cls, macro_line: str, precision: int = 4) -> str:
        """Format an Okuma macro or cycle line ensuring correct spacing.

        Strictly enforces space padding inside relational operator brackets:
        e.g. 'IF [VC1 LE 5] N100'.
        """
        # Enforce 'IF [' with space
        if macro_line.upper().startswith("IF["):
            macro_line = "IF [" + macro_line[3:]
        elif macro_line.upper().startswith("IF ["):
            macro_line = "IF [" + macro_line[macro_line.find("[") + 1:]

        # Enforce spaces around relational operators inside brackets: LT, LE, EQ, NE, GT, GE
        def bracket_replacer(match: re.Match) -> str:
            content = match.group(1).strip()
            # Normalize internal operator spacing
            for op in ("LE", "LT", "GE", "GT", "EQ", "NE"):
                pattern = re.compile(rf"\s*{op}\s*", re.IGNORECASE)
                content = pattern.sub(f" {op.upper()} ", content)
            return f"[{content}]"

        formatted = re.sub(r"\[(.*?)\]", bracket_replacer, macro_line)
        # Ensure space between ] and target label or GOTO: e.g. ]N100 -> ] N100
        formatted = re.sub(r"\]\s*([NG])", r"] \1", formatted)
        return formatted



class ModalTracker:
    """Tracks active CNC modal state and suppresses redundant commands and coordinates.

    Modal groups tracked:
    - Motion group: G0, G1, G2, G3
    - Plane group: G17, G18, G19
    - Distance mode: G90, G91
    - Feed mode: G94, G95
    - Active coordinates: X, Y, Z, A, B, C
    - Active parameters: F (feedrate), S (spindle speed)
    """

    def __init__(self, tolerance: float = 1e-4) -> None:
        """Initialize modal tracker.

        Args:
            tolerance: Positional difference threshold below which an axis move is suppressed.
        """
        self.tolerance = tolerance
        self.motion_mode: Optional[str] = None  # G0, G1, G2, G3
        self.plane: Optional[str] = "G17"
        self.distance_mode: Optional[str] = "G90"
        self.feed_mode: Optional[str] = None
        self.coords: Dict[str, float] = {}
        self.feedrate: Optional[float] = None
        self.spindle_speed: Optional[float] = None
        self.work_offset: Optional[str] = None

    def reset(self) -> None:
        """Reset all modal registers."""
        self.motion_mode = None
        self.plane = "G17"
        self.distance_mode = "G90"
        self.feed_mode = None
        self.coords.clear()
        self.feedrate = None
        self.spindle_speed = None
        self.work_offset = None

    def filter_command(
        self,
        motion: Optional[str],
        axes: Dict[str, float],
        feedrate: Optional[float] = None,
        spindle: Optional[float] = None,
        force_motion: bool = False,
    ) -> Tuple[Optional[str], Dict[str, float], Optional[float], Optional[float]]:
        """Filter command attributes against active modal state.

        Args:
            motion: Candidate motion code (e.g. 'G0', 'G1', 'G2', 'G3').
            axes: Candidate coordinate mappings (e.g. {'X': 10.0, 'Y': 20.0}).
            feedrate: Candidate feedrate.
            spindle: Candidate spindle speed.
            force_motion: Force emission of motion code even if modal.

        Returns:
            Tuple of (emitted_motion, emitted_axes, emitted_feedrate, emitted_spindle).
        """
        emit_motion: Optional[str] = None
        if motion:
            norm_motion = GCodeCompressor.abbreviate_code(motion.upper())
            if force_motion or norm_motion != self.motion_mode:
                emit_motion = norm_motion
                self.motion_mode = norm_motion

        emit_axes: Dict[str, float] = {}
        for axis, val in axes.items():
            axis_upper = axis.upper()
            if axis_upper in ("I", "J", "K", "R"):
                # Circular interpolation parameters are non-modal per block
                emit_axes[axis_upper] = val
            else:
                prev_val = self.coords.get(axis_upper)
                if prev_val is None or abs(val - prev_val) > self.tolerance:
                    emit_axes[axis_upper] = val
                    self.coords[axis_upper] = val

        emit_feed: Optional[float] = None
        if feedrate is not None and feedrate > 0:
            if self.feedrate is None or abs(feedrate - self.feedrate) > 1e-3:
                emit_feed = feedrate
                self.feedrate = feedrate

        emit_spindle: Optional[float] = None
        if spindle is not None and spindle > 0:
            if self.spindle_speed is None or abs(spindle - self.spindle_speed) > 1e-3:
                emit_spindle = spindle
                self.spindle_speed = spindle

        return emit_motion, emit_axes, emit_feed, emit_spindle


class PatternRecognizer:
    """Recognizes geometric hole coordinate patterns for Okuma pattern calculation functions.

    Generates:
    - BHC: Bolt Hole Circle (Xp, Yp, I_radius, J_start_angle, K_count)
    - ARC: Arc pattern (Xp, Yp, I_radius, Q_angle_inc, K_count, J_start_angle)
    - GRDX / GRDY: Grid array along X or Y axis (Xp, Yp, I_dx, J_dy, K_nx, P_ny)
    - LAA: Line at angle (Xp, Yp, I_dist, K_count, J_angle)
    - M52: Final hole Z upper limit retract modifier
    """

    def __init__(self, tolerance: float = 1e-3) -> None:
        self.tolerance = tolerance

    def recognize_bolt_hole_circle(
        self,
        holes: Sequence[Tuple[float, float]],
        m52_retract: bool = True,
        precision: int = 4,
    ) -> Optional[str]:
        """Detect whether hole coordinates form a Bolt Hole Circle (BHC).

        BHC Format:
            BHC Xp_ Yp_ I_radius J_start_angle K_hole_count [M52]

        Args:
            holes: Sequence of (X, Y) hole coordinate tuples (minimum 3 holes).
            m52_retract: Whether to append M52 (upper limit retract) modifier.
            precision: Decimal precision for coordinates.

        Returns:
            Formatted Okuma BHC line if pattern matches, else None.
        """
        n = len(holes)
        if n < 3:
            return None

        # Calculate centroid (Xp, Yp)
        cx = sum(x for x, y in holes) / n
        cy = sum(y for x, y in holes) / n

        # Calculate radii from centroid
        radii = [math.hypot(x - cx, y - cy) for x, y in holes]
        avg_r = sum(radii) / n
        if avg_r < self.tolerance:
            return None

        # Check radius uniformity
        if any(abs(r - avg_r) > self.tolerance for r in radii):
            return None

        # Calculate angles in degrees [0, 360)
        angles = [math.degrees(math.atan2(y - cy, x - cx)) % 360.0 for x, y in holes]
        # Sort angles or verify stepping
        sorted_indices = sorted(range(n), key=lambda i: angles[i])
        sorted_angles = [angles[i] for i in sorted_indices]

        # Calculate expected angular increment for full circle
        expected_inc = 360.0 / n
        is_full_circle = True
        for i in range(n):
            next_i = (i + 1) % n
            diff = (sorted_angles[next_i] - sorted_angles[i]) % 360.0
            if abs(diff - expected_inc) > 0.1:
                is_full_circle = False
                break

        if not is_full_circle:
            return None

        # Determine start angle J from first hole in original sequence
        first_x, first_y = holes[0]
        start_angle = math.degrees(math.atan2(first_y - cy, first_x - cx)) % 360.0

        # Check direction (CCW positive K, CW negative K)
        second_x, second_y = holes[1]
        second_angle = math.degrees(math.atan2(second_y - cy, second_x - cx)) % 360.0
        step_diff = (second_angle - start_angle) % 360.0
        k_val = n
        if abs(step_diff - (360.0 - expected_inc)) < 0.1:
            k_val = -n  # CW stepping

        xp_s = GCodeCompressor.format_number(cx, precision)
        yp_s = GCodeCompressor.format_number(cy, precision)
        r_s = GCodeCompressor.format_number(avg_r, precision)
        j_s = GCodeCompressor.format_number(start_angle, precision)

        m52_str = " M52" if m52_retract else ""
        return f"BHC X{xp_s} Y{yp_s} I{r_s} J{j_s} K{k_val}{m52_str}"

    def recognize_grid(
        self,
        holes: Sequence[Tuple[float, float]],
        m52_retract: bool = True,
        precision: int = 4,
    ) -> Optional[str]:
        """Detect whether hole coordinates form a regular grid array (GRDX / GRDY).

        GRDX Format:
            GRDX Xp_ Yp_ I±dx J±dy Knx Pny [M52]

        Args:
            holes: Sequence of (X, Y) hole coordinate tuples (minimum 4 holes).
            m52_retract: Append M52 retract.
            precision: Decimal precision.

        Returns:
            Formatted Okuma GRDX or GRDY line if pattern matches, else None.
        """
        n = len(holes)
        if n < 4:
            return None

        xs = sorted(list({round(x, precision) for x, _ in holes}))
        ys = sorted(list({round(y, precision) for _, y in holes}))

        nx = len(xs)
        ny = len(ys)
        if nx < 2 or ny < 2 or (nx * ny != n):
            return None

        # Verify regular spacing along X
        dx = (xs[-1] - xs[0]) / (nx - 1)
        for i in range(len(xs) - 1):
            if abs((xs[i + 1] - xs[i]) - dx) > self.tolerance:
                return None

        # Verify regular spacing along Y
        dy = (ys[-1] - ys[0]) / (ny - 1)
        for j in range(len(ys) - 1):
            if abs((ys[j + 1] - ys[j]) - dy) > self.tolerance:
                return None

        # Verify that all grid points exist
        hole_set = {(round(x, precision), round(y, precision)) for x, y in holes}
        for x in xs:
            for y in ys:
                if (x, y) not in hole_set:
                    return None

        # Determine reference point Xp, Yp from first hole in order
        x0, y0 = holes[0]
        # Match scan direction (X-primary GRDX or Y-primary GRDY)
        mnemonic = "GRDX"
        if len(holes) > 1 and abs(holes[1][0] - x0) < self.tolerance:
            mnemonic = "GRDY"

        xp_s = GCodeCompressor.format_number(x0, precision)
        yp_s = GCodeCompressor.format_number(y0, precision)
        dx_s = GCodeCompressor.format_number(dx, precision)
        dy_s = GCodeCompressor.format_number(dy, precision)

        m52_str = " M52" if m52_retract else ""
        return f"{mnemonic} X{xp_s} Y{yp_s} I{dx_s} J{dy_s} K{nx} P{ny}{m52_str}"

    def recognize_line_at_angle(
        self,
        holes: Sequence[Tuple[float, float]],
        m52_retract: bool = True,
        precision: int = 4,
    ) -> Optional[str]:
        """Detect whether hole coordinates form a Line at Angle (LAA).

        LAA Format:
            LAA Xp_ Yp_ I±dist Kcount Jangle [M52]

        Args:
            holes: Sequence of (X, Y) hole coordinate tuples (minimum 3 holes).
            m52_retract: Append M52 retract.
            precision: Decimal precision.

        Returns:
            Formatted Okuma LAA line if pattern matches, else None.
        """
        n = len(holes)
        if n < 3:
            return None

        x0, y0 = holes[0]
        x1, y1 = holes[1]
        dist = math.hypot(x1 - x0, y1 - y0)
        if dist < self.tolerance:
            return None

        angle = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 360.0

        for i in range(1, n):
            xi, yi = holes[i]
            expected_x = x0 + i * dist * math.cos(math.radians(angle))
            expected_y = y0 + i * dist * math.sin(math.radians(angle))
            if math.hypot(xi - expected_x, yi - expected_y) > self.tolerance:
                return None

        xp_s = GCodeCompressor.format_number(x0, precision)
        yp_s = GCodeCompressor.format_number(y0, precision)
        dist_s = GCodeCompressor.format_number(dist, precision)
        angle_s = GCodeCompressor.format_number(angle, precision)

        m52_str = " M52" if m52_retract else ""
        return f"LAA X{xp_s} Y{yp_s} I{dist_s} K{n} J{angle_s}{m52_str}"


class AreaMachiningEngine:
    """Generates native Okuma OSP Area Machining commands.

    Commands supported:
    - FMILR: Face milling roughing (zigzag on-workpiece)
    - FMILF: Face milling finishing (parallel off-workpiece)
    - PMIL:  Rectangular pocket milling (zigzag + perimeter clean-up)
    - PMILR: Rectangular pocket milling (spiral)
    - RMILO: Outer perimeter milling
    - RMILI: Inner perimeter milling

    General format per Okuma OSP specification:
        [Mnemonic] Xp_ Yp_ Zp_ I±dx J±dy K_ P_ Q_ R_ D_ F_ FA=_ FB=_
    """

    @classmethod
    def generate_command(
        cls,
        mnemonic: str,
        xp: float,
        yp: float,
        zp: float,
        idx: float,
        jdy: float,
        q_stepdown: Optional[float] = None,
        r_rapid_level: Optional[float] = None,
        k_allowance: float = 0.0,
        p_stepover_ratio: float = 70.0,
        d_offset_num: int = 1,
        feedrate: float = 250.0,
        fa_transition_feed: Optional[float] = None,
        fb_infeed_feed: Optional[float] = None,
        precision: int = 4,
    ) -> str:
        """Construct a native Okuma area machining block.

        Args:
            mnemonic: Operation mnemonic (FMILR, FMILF, PMIL, PMILR, RMILO, RMILI).
            xp: X reference point.
            yp: Y reference point.
            zp: Z finish level.
            idx: Length along X-axis (+/- dx).
            jdy: Length along Y-axis (+/- dy).
            q_stepdown: Axial depth per cut (Z stepdown).
            r_rapid_level: Rapid return level (clearance).
            k_allowance: Finish allowance on walls/bottom.
            p_stepover_ratio: Stepover ratio as percentage of cutter diameter (default 70).
            d_offset_num: Cutter compensation register number (D1-D99).
            feedrate: Cutting feedrate F.
            fa_transition_feed: Transition feedrate FA= (defaults to 4 * F).
            fb_infeed_feed: Z infeed feedrate FB= (defaults to F / 4).
            precision: Decimal precision.

        Returns:
            Fully-formatted Okuma Area Machining G-code line.
        """
        mnemonic_upper = mnemonic.upper()
        tokens = [mnemonic_upper]

        tokens.append(f"X{GCodeCompressor.format_number(xp, precision)}")
        tokens.append(f"Y{GCodeCompressor.format_number(yp, precision)}")
        tokens.append(f"Z{GCodeCompressor.format_number(zp, precision)}")
        tokens.append(f"I{GCodeCompressor.format_number(idx, precision)}")
        tokens.append(f"J{GCodeCompressor.format_number(jdy, precision)}")

        if abs(k_allowance) > 1e-6:
            tokens.append(f"K{GCodeCompressor.format_number(k_allowance, precision)}")

        tokens.append(f"P{GCodeCompressor.format_number(p_stepover_ratio, precision, keep_decimal_point=False)}")

        if q_stepdown is not None and q_stepdown > 0:
            tokens.append(f"Q{GCodeCompressor.format_number(q_stepdown, precision)}")

        if r_rapid_level is not None:
            tokens.append(f"R{GCodeCompressor.format_number(r_rapid_level, precision)}")

        tokens.append(f"D{int(d_offset_num)}")
        tokens.append(f"F{GCodeCompressor.format_number(feedrate, precision)}")

        fa = fa_transition_feed if fa_transition_feed is not None else (4.0 * feedrate)
        fb = fb_infeed_feed if fb_infeed_feed is not None else (feedrate / 4.0)

        tokens.append(f"FA={GCodeCompressor.format_number(fa, precision)}")
        tokens.append(f"FB={GCodeCompressor.format_number(fb, precision)}")

        return " ".join(tokens)

    @classmethod
    def generate_circular_pocket_command(
        cls,
        xc: float,
        yc: float,
        zp: float,
        radius: float,
        q_stepdown: Optional[float] = None,
        r_rapid_level: Optional[float] = None,
        k_allowance: float = 0.0,
        d_offset_num: int = 1,
        feedrate: float = 250.0,
        precision: int = 4,
    ) -> str:
        """Construct a compact circular/helical milling command for cylindrical core.

        Uses Okuma circular pocket format or G02 helical infeed.
        Format:
            G2 X<xc> Y<yc> Z<zp> I<radius> J0. F<feed>
        """
        xc_s = GCodeCompressor.format_number(xc, precision)
        yc_s = GCodeCompressor.format_number(yc, precision)
        zp_s = GCodeCompressor.format_number(zp, precision)
        rad_s = GCodeCompressor.format_number(radius, precision)
        f_s = GCodeCompressor.format_number(feedrate, precision)
        tokens = ["G2", f"X{xc_s}", f"Y{yc_s}", f"Z{zp_s}", f"I{rad_s}", "J0.", f"F{f_s}"]
        if d_offset_num:
            tokens.append(f"D{int(d_offset_num)}")
        return " ".join(tokens)


class SubprogramManager:
    """Extracts repetitive 2D contour toolpaths into Okuma subprograms (.SUB).

    Features:
    - Generates .SUB subprogram files starting with O<id> and ending with RTS.
    - Generates CALL loops or MODIN/MODOUT modal calls in main .MIN programs.
    - Observes Okuma relational operator spacing (e.g. IF [VC1 LE 5] N100).
    - Preserves G111 for OTCHK (TOOLCHK.LIB) without collision.
    """

    def __init__(self, start_sub_id: int = 100) -> None:
        self.next_sub_id = start_sub_id
        self.subprograms: Dict[int, List[str]] = {}

    def create_subprogram(self, lines: Sequence[str], sub_id: Optional[int] = None) -> int:
        """Register a new subprogram containing given G-code lines.

        Args:
            lines: G-code lines forming the subprogram body.
            sub_id: Optional custom subprogram ID (e.g. 100).

        Returns:
            Assigned subprogram ID.
        """
        sid = sub_id if sub_id is not None else self.next_sub_id
        if sid >= self.next_sub_id:
            self.next_sub_id = sid + 1

        self.subprograms[sid] = list(lines)
        return sid

    def generate_sub_file_content(self, sub_id: int) -> str:
        """Generate complete .SUB file content for a given subprogram.

        Format:
            O<sub_id>
            ... body lines ...
            RTS
        """
        lines = self.subprograms.get(sub_id, [])
        header = f"O{sub_id:04d}"
        body = "\n".join(lines)
        footer = "RTS"
        return f"{header}\n{body}\n{footer}\n"

    @staticmethod
    def generate_call_loop(

        sub_id: int,
        start_z: float,
        final_z: float,
        stepdown: float,
        feedrate: float,
        var_num: int = 1,
        precision: int = 4,
    ) -> List[str]:
        """Generate a simple User Task macro loop in main .MIN calling subprogram."""
        loop_lines = []
        lbl = 100
        var_name = f"VC{var_num}"

        z_init = GCodeCompressor.format_number(start_z - stepdown, precision)
        z_final = GCodeCompressor.format_number(final_z, precision)
        step_str = GCodeCompressor.format_number(stepdown, precision)

        loop_lines.append(f"{var_name}={z_init}")
        loop_lines.append(f"N{lbl}")
        loop_lines.append(f"G0 Z[{var_name}+1.]")
        loop_lines.append(f"G1 Z[{var_name}] F{GCodeCompressor.format_number(feedrate, precision)}")
        loop_lines.append(f"CALL O{sub_id:04d}")
        loop_lines.append(f"{var_name}={var_name}-{step_str}")
        loop_lines.append(f"IF [{var_name} GE {z_final}] N{lbl}")

        return loop_lines

    def create_parametric_subprogram(

        self,
        slice_commands: List[Tuple[str, Dict[str, float]]],
        sub_id: Optional[int] = None,
        feedrate: float = 250.0,
        plunge_feedrate: Optional[float] = None,
        precision: int = 4,
    ) -> int:
        """Register a parametric 2D clearing subprogram.

        Uses local address arguments PZ (target depth) and PR (rapid/plunge clearance).

        Format:
            O<sub_id>
            ( PARAMETRIC CLEARING SUBPROGRAM: PZ=DEPTH, PR=CLEARANCE )
            G0 Z[PZ+PR]
            G1 Z[PZ] F<plunge_feed>
            ... (2D XY commands) ...
            G0 Z[PZ+PR]
            RTS
        """
        sid = sub_id if sub_id is not None else self.next_sub_id
        if sid >= self.next_sub_id:
            self.next_sub_id = sid + 1

        p_feed = plunge_feedrate if plunge_feedrate is not None else (feedrate / 4.0)

        lines = [
            "( PARAMETRIC CLEARING SUBPROGRAM: PZ=DEPTH, PR=CLEARANCE )",
            "G0 Z[PZ+PR]",
            f"G1 Z[PZ] F{GCodeCompressor.format_number(p_feed, precision)}",
        ]

        modal = ModalTracker()
        for cmd_name, params in slice_commands:
            m_upper = cmd_name.upper()
            axes = {k: v for k, v in params.items() if k in ("X", "Y", "A", "B", "I", "J", "K")}
            f_val = params.get("F", feedrate)
            em_motion, em_axes, em_f, _ = modal.filter_command(m_upper, axes, feedrate=f_val)
            tokens = []
            if em_motion:
                tokens.append(GCodeCompressor.abbreviate_code(em_motion))
            for ax in sorted(em_axes.keys()):
                val_s = GCodeCompressor.format_number(em_axes[ax], precision)
                tokens.append(f"{ax}{val_s}")
            if em_f is not None:
                tokens.append(f"F{GCodeCompressor.format_number(em_f, precision)}")
            if tokens:
                lines.append(" ".join(tokens))

        lines.append("G0 Z[PZ+PR]")
        self.subprograms[sid] = lines
        return sid

    @staticmethod
    def generate_parametric_loop(
        sub_id: int,
        start_z: float,
        final_z: float,
        stepdown: float,
        plunge_clearance: float = 2.0,
        draft_mode: str = "none",  # "none", "scale", "offset"
        centroid: Tuple[float, float] = (0.0, 0.0),
        scale_start: float = 1.0,
        scale_step: float = 0.0,
        offset_start: float = 0.0,
        offset_step: float = 0.0,
        var_scope: str = "local",  # "local" (LA-LE) or "common" (VC33+)
        start_vc: int = 33,
        precision: int = 4,
    ) -> List[str]:
        """Generate parametric loop in main program (.MIN) calling subprogram."""
        lines = []
        lbl = 100

        z_first = start_z - stepdown
        z_init = GCodeCompressor.format_number(z_first, precision)
        z_step_s = GCodeCompressor.format_number(stepdown, precision)
        z_fin_s = GCodeCompressor.format_number(final_z, precision)
        pr_s = GCodeCompressor.format_number(plunge_clearance, precision)

        is_local = "local" in var_scope.lower()
        if is_local:
            v_z = "LA"
            v_step = "LB"
            v_final = "LC"
            v_draft = "LD"
            v_dstep = "LE"
        else:
            v_z = f"VC{start_vc}"
            v_step = f"VC{start_vc+1}"
            v_final = f"VC{start_vc+2}"
            v_draft = f"VC{start_vc+3}"
            v_dstep = f"VC{start_vc+4}"


        lines.append(f"{v_z}={z_init}")
        lines.append(f"{v_step}={z_step_s}")
        lines.append(f"{v_final}={z_fin_s}")

        if draft_mode == "scale":
            lines.append(f"{v_draft}={GCodeCompressor.format_number(scale_start, precision)}")
            lines.append(f"{v_dstep}={GCodeCompressor.format_number(scale_step, precision)}")
        elif draft_mode == "offset":
            lines.append(f"{v_draft}={GCodeCompressor.format_number(offset_start, precision)}")
            lines.append(f"{v_dstep}={GCodeCompressor.format_number(offset_step, precision)}")

        lines.append(f"N{lbl}")

        if draft_mode == "scale":
            cx_s = GCodeCompressor.format_number(centroid[0], precision)
            cy_s = GCodeCompressor.format_number(centroid[1], precision)
            lines.append(f"G51 X{cx_s} Y{cy_s} P[{v_draft}]")
            lines.append(f"CALL O{sub_id:04d} PZ=[{v_z}] PR={pr_s}")
            lines.append("G50")
            lines.append(f"{v_draft}={v_draft}-{v_dstep}")
        elif draft_mode == "offset":
            lines.append(f"CALL O{sub_id:04d} PZ=[{v_z}] PR={pr_s} PD=[{v_draft}]")
            lines.append(f"{v_draft}={v_draft}+{v_dstep}")
        else:
            lines.append(f"CALL O{sub_id:04d} PZ=[{v_z}] PR={pr_s}")

        lines.append(f"{v_z}={v_z}-{v_step}")
        # Enforce spaces around relational operator GE
        lines.append(f"IF [{v_z} GE {v_final}] N{lbl}")

        return lines


class ZSlice:
    """Represents a 2D planar cutting pass at a constant Z height."""

    def __init__(
        self,
        depth: float,
        commands: List[Tuple[str, Dict[str, float]]],
        plunge_cmd: Optional[Tuple[str, Dict[str, float]]] = None,
    ) -> None:
        self.depth = depth
        self.commands = commands
        self.plunge_cmd = plunge_cmd
        self._calc_bounds()

    def _calc_bounds(self) -> None:
        xs = [p["X"] for _, p in self.commands if "X" in p]
        ys = [p["Y"] for _, p in self.commands if "Y" in p]
        if xs and ys:
            self.min_x = min(xs)
            self.max_x = max(xs)
            self.min_y = min(ys)
            self.max_y = max(ys)
            self.center_x = (self.min_x + self.max_x) / 2.0
            self.center_y = (self.min_y + self.max_y) / 2.0
            self.span_x = self.max_x - self.min_x
            self.span_y = self.max_y - self.min_y
        else:
            self.min_x = self.max_x = self.center_x = self.span_x = 0.0
            self.min_y = self.max_y = self.center_y = self.span_y = 0.0


class ZSliceSegmenter:
    """Segments an operation's commands into discrete planar Z-slices."""

    def __init__(self, z_tolerance: float = 1e-3, min_commands_per_slice: int = 3) -> None:
        self.z_tolerance = z_tolerance
        self.min_commands_per_slice = min_commands_per_slice

    def segment(self, commands: Sequence[Any]) -> List[ZSlice]:
        slices: List[ZSlice] = []
        current_z: Optional[float] = None
        current_cmds: List[Tuple[str, Dict[str, float]]] = []
        current_plunge: Optional[Tuple[str, Dict[str, float]]] = None

        for cmd in commands:
            if hasattr(cmd, "Name"):
                cname = cmd.Name.upper()
                params = dict(cmd.Parameters)
            else:
                cname = cmd[0].upper()
                params = dict(cmd[1])

            if cname.startswith("(") or cname.startswith(";"):
                continue

            z_in_cmd = "Z" in params
            new_z = params.get("Z")

            if z_in_cmd:
                if current_z is None:
                    current_z = new_z
                    current_plunge = (cname, params)
                elif abs(new_z - current_z) > self.z_tolerance:
                    cutting_moves = [c for c in current_cmds if c[0] in ("G1", "G01", "G2", "G02", "G3", "G03")]
                    if len(cutting_moves) >= self.min_commands_per_slice:
                        slices.append(ZSlice(depth=current_z, commands=current_cmds, plunge_cmd=current_plunge))

                    current_z = new_z
                    current_cmds = []
                    current_plunge = (cname, params)
                    continue

            if cname in ("G0", "G00", "G1", "G01", "G2", "G02", "G3", "G03"):
                current_cmds.append((cname, params))

        if current_z is not None and current_cmds:
            cutting_moves = [c for c in current_cmds if c[0] in ("G1", "G01", "G2", "G02", "G3", "G03")]
            if len(cutting_moves) >= self.min_commands_per_slice:
                slices.append(ZSlice(depth=current_z, commands=current_cmds, plunge_cmd=current_plunge))

        return slices


class SliceSimilarityClassifier:
    """Classifies geometric relationships between consecutive Z-slices."""

    def __init__(self, tolerance: float = 1e-3) -> None:
        self.tolerance = tolerance

    def classify(self, slices: Sequence[ZSlice], min_slices: int = 3) -> Tuple[str, Dict[str, Any]]:
        if len(slices) < min_slices:
            return "INLINE", {}

        # 1. Check for IDENTICAL (straight vertical walls)
        ref_slice = slices[0]
        ref_cmds = ref_slice.commands
        is_identical = True

        for s in slices[1:]:
            if len(s.commands) != len(ref_cmds):
                is_identical = False
                break
            for (c1_name, c1_p), (c2_name, c2_p) in zip(ref_cmds, s.commands):
                if GCodeCompressor.abbreviate_code(c1_name) != GCodeCompressor.abbreviate_code(c2_name):
                    is_identical = False
                    break
                for ax in ("X", "Y", "I", "J"):
                    v1 = c1_p.get(ax)
                    v2 = c2_p.get(ax)
                    if (v1 is None) != (v2 is None):
                        is_identical = False
                        break
                    if v1 is not None and abs(v1 - v2) > self.tolerance:
                        is_identical = False
                        break
                if not is_identical:
                    break
            if not is_identical:
                break

        stepdowns = [abs(slices[i].depth - slices[i+1].depth) for i in range(len(slices)-1)]
        avg_stepdown = sum(stepdowns) / len(stepdowns) if stepdowns else 2.0

        if is_identical:
            return "IDENTICAL", {
                "stepdown": avg_stepdown,
                "start_z": slices[0].depth + avg_stepdown,
                "final_z": slices[-1].depth,
                "slice_count": len(slices),
                "centroid": (ref_slice.center_x, ref_slice.center_y),
            }

        # 2. Check for DRAFTED_SCALED (tapered cavity)
        ref_span = ref_slice.span_x if ref_slice.span_x > 0 else ref_slice.span_y
        if ref_span > self.tolerance:
            scale_ratios = []
            for s in slices:
                s_span = s.span_x if s.span_x > 0 else s.span_y
                scale_ratios.append(s_span / ref_span)

            scale_deltas = [scale_ratios[i] - scale_ratios[i+1] for i in range(len(scale_ratios)-1)]
            avg_scale_delta = sum(scale_deltas) / len(scale_deltas) if scale_deltas else 0.0

            if avg_scale_delta > 1e-4 and all(abs(d - avg_scale_delta) < 0.05 for d in scale_deltas):
                delta_r = (avg_scale_delta * ref_span) / 2.0
                draft_angle = math.degrees(math.atan2(delta_r, avg_stepdown))
                return "DRAFTED_SCALED", {
                    "stepdown": avg_stepdown,
                    "start_z": slices[0].depth + avg_stepdown,
                    "final_z": slices[-1].depth,
                    "scale_start": scale_ratios[0],
                    "scale_step": avg_scale_delta,
                    "draft_angle": draft_angle,
                    "centroid": (ref_slice.center_x, ref_slice.center_y),
                    "slice_count": len(slices),
                }

        return "UNIQUE", {}



class OkumaOptimizer:
    """Master optimizer combining compression, modal tracking, pattern recognition, and macros."""

    def __init__(
        self,
        precision: int = 4,
        strip_whitespace: bool = False,
        enable_modal: bool = True,
        enable_patterns: bool = True,
        enable_area_machining: bool = True,
    ) -> None:
        self.precision = precision
        self.strip_whitespace = strip_whitespace
        self.enable_modal = enable_modal
        self.enable_patterns = enable_patterns
        self.enable_area_machining = enable_area_machining

        self.compressor = GCodeCompressor()
        self.modal = ModalTracker()
        self.patterns = PatternRecognizer()
        self.subprograms = SubprogramManager()

    def reset(self) -> None:
        """Reset internal optimizer state."""
        self.modal.reset()

    def optimize_block(
        self,
        motion: Optional[str],
        axes: Dict[str, float],
        feedrate: Optional[float] = None,
        spindle: Optional[float] = None,
        force_motion: bool = False,
    ) -> str:
        """Optimize a motion block through modal suppression and character compression."""
        if self.enable_modal:
            emit_motion, emit_axes, emit_feed, emit_spindle = self.modal.filter_command(
                motion=motion,
                axes=axes,
                feedrate=feedrate,
                spindle=spindle,
                force_motion=force_motion,
            )
        else:
            emit_motion = GCodeCompressor.abbreviate_code(motion) if motion else None
            emit_axes = axes
            emit_feed = feedrate
            emit_spindle = spindle

        tokens = []
        if emit_motion:
            tokens.append(emit_motion)
        for ax in sorted(emit_axes.keys()):
            val_s = GCodeCompressor.format_number(emit_axes[ax], self.precision)
            tokens.append(f"{ax}{val_s}")
        if emit_feed is not None:
            tokens.append(f"F{GCodeCompressor.format_number(emit_feed, self.precision)}")
        if emit_spindle is not None:
            tokens.append(f"S{int(emit_spindle)}")

        join_char = "" if self.strip_whitespace else " "
        return join_char.join(tokens)
