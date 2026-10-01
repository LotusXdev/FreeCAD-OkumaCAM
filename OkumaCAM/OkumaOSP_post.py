"""FreeCAD CAM Post-Processor for Okuma OSP (OSP7000 / OSP-P series) CNC Controls.

Features:
- Size-optimized G-code generation with aggressive modal tracking and zero-stripping.
- Automatic conversion of FreeCAD CAM internal mm/s feedrates to mm/min or IPM using FreeCAD.Units.
- Native Okuma OSP Area Machining functions (FMILR/FMILF, PMIL/PMILR, RMILO/RMILI).
- Coordinate calculation pattern functions (BHC, ARC, GRDX, GRDY, LAA, M52).
- Dedicated G111 Tool Check macro mapping for OTCHK (TOOLCHK.LIB).
- Optional subprogram extraction (.SUB with RTS) and parametric CALL/MODIN loops.
"""

from __future__ import annotations

import datetime
import json
import math
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import FreeCAD as App
from FreeCAD import Units
import Path
import PathScripts.PathUtils as PathUtils

# Ensure OkumaOptimizer is importable from same directory
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from OkumaOptimizer import (
    AreaMachiningEngine,
    GCodeCompressor,
    ModalTracker,
    OkumaOptimizer as OptimizerEngine,
    PatternRecognizer,
    SliceSimilarityClassifier,
    SubprogramManager,
    ZSlice,
    ZSliceSegmenter,
)

TOOLTIP = """
Okuma OSP Post-Processor for FreeCAD CAM.
Outputs size-optimized G-code for Okuma OSP controls (OSP7000, OSP-P series).
Supports native area machining (FMILR/PMIL), pattern cycles (BHC/GRDX),
tool check routines (G111 OTCHK in TOOLCHK.LIB), subprogram extraction (.SUB),
Electric Spindle Speeder integration (M130/M131/dual-M00), and separate rough/finish program export.
"""

TOOLTIP_ARGS = """
Arguments for OkumaOSP:
    --header, --no-header                 ... Output program header/metadata (Default: --header)
    --comments, --no-comments             ... Output comments in G-code (Default: --comments)
    --line-numbers, --no-line-numbers     ... Prefix lines with N-numbers (Default: --no-line-numbers)
    --modal, --no-modal                   ... Suppress modal coordinates & codes (Default: --modal)
    --toolcheck, --no-toolcheck           ... Emit G111 T_ tool check for OTCHK in TOOLCHK.LIB (Default: --no-toolcheck)
    --native-cycles, --no-native-cycles   ... Emit FMILR/PMIL/BHC native cycles when matched (Default: --native-cycles)
    --subprograms, --no-subprograms       ... Extract multi-pass contours into .SUB file (Default: --no-subprograms)
    --auto-slices, --no-auto-slices       ... Extract repeating Z-slices in pockets to .SUB (Default: --auto-slices)
    --draft-mode=scale|offset|none        ... Drafted wall strategy (Default: scale)
    --min-slices=3                        ... Minimum slices to extract subprogram (Default: 3)
    --var-scope=local|common              ... Loop variables LA-LD or VC33+ (Default: local)
    --compress, --no-compress             ... Strip unnecessary whitespace (Default: --compress)
    --precision=4                         ... Decimal precision for coordinates (Default: 4)
    --feed-precision=1                    ... Decimal precision for feedrates (Default: 1)
    --inches                              ... Output imperial units (G20, in/min)
    --metric                              ... Output metric units (G21, mm/min)
    --speeder, --no-speeder               ... Enable Electric Spindle Speeder mode (Default: --no-speeder)
    --speeder-scope=finish|all|rough      ... Speeder application scope (Default: finish)
    --speeder-dual-m00, --no-speeder-dual-m00 ... Enforce dual M00 orientation stops (Default: --speeder-dual-m00)
    --speeder-verify, --no-speeder-verify ... Verify zero main spindle movement after speeder load (Default: --speeder-verify)
    --speeder-retract=200.0               ... Safe Z retract height for speeder unload (Default: 200.0)
    --separate-rough-finish, --no-separate-rough-finish ... Export roughing and finishing as separate files (Default: --no-separate-rough-finish)
    --rough-suffix=_ROUGH                 ... Suffix for roughing program (Default: _ROUGH)
    --finish-suffix=_FINISH               ... Suffix for finishing program (Default: _FINISH)
"""

class SpeederPostError(Exception):
    """Raised when unsafe spindle movement or setup error is detected in electric speeder mode."""
    pass


class PostResult(tuple):
    """Result tuple supporting 2-element unpack and rich attribute access for separate exports."""
    def __new__(cls, first_item: str, second_item: Optional[str] = None,
                rough_main: Optional[str] = None, finish_main: Optional[str] = None,
                rough_sub: Optional[str] = None, finish_sub: Optional[str] = None,
                files_written: Optional[List[str]] = None):
        return super().__new__(cls, (first_item, second_item))

    def __init__(self, first_item: str, second_item: Optional[str] = None,
                 rough_main: Optional[str] = None, finish_main: Optional[str] = None,
                 rough_sub: Optional[str] = None, finish_sub: Optional[str] = None,
                 files_written: Optional[List[str]] = None):
        self.main_code = first_item
        self.sub_code = second_item
        self.rough_main = rough_main or first_item
        self.finish_main = finish_main
        self.rough_sub = rough_sub
        self.finish_sub = finish_sub
        self.files_written = files_written or []


# Global configuration defaults
OUTPUT_HEADER: bool = True
OUTPUT_COMMENTS: bool = True
OUTPUT_LINE_NUMBERS: bool = False
ENABLE_MODAL: bool = True
ENABLE_TOOLCHECK: bool = False
ENABLE_NATIVE_CYCLES: bool = True
ENABLE_SUBPROGRAMS: bool = False
ENABLE_AUTO_SLICES: bool = True
DRAFT_MODE: str = "scale"
MIN_SLICES: int = 3
VAR_SCOPE: str = "local"
START_VC: int = 33
ENABLE_COMPRESSION: bool = True
COORDINATE_PRECISION: int = 4
FEED_PRECISION: int = 1

# Electric Spindle Speeder defaults (okuma-electric-speeder-supplement-v2)
ENABLE_SPEEDER: bool = False
SPEEDER_SCOPE: str = "finish"  # "finish", "all", "rough"
SPEEDER_DUAL_M00: bool = True
SPEEDER_VERIFY: bool = True
SPEEDER_RETRACT_Z: float = 200.0

# Multi-program separate rough/finish export defaults
SEPARATE_ROUGH_FINISH: bool = False
ROUGH_SUFFIX: str = "_ROUGH"
FINISH_SUFFIX: str = "_FINISH"

UNITS: str = "G21"  # G21 for metric, G20 for imperial
UNIT_FORMAT: str = "mm"
UNIT_SPEED_FORMAT: str = "mm/min"

PROGRAM_NUMBER: int = 1000
WORK_FIXTURE: str = "G15 H1"


def load_user_preferences() -> None:
    """Load configuration from FreeCAD BaseApp preferences if available."""
    try:
        param_grp = App.ParamGet("User parameter:BaseApp/Preferences/Mod/OkumaCAM")
        global ENABLE_TOOLCHECK, ENABLE_NATIVE_CYCLES, ENABLE_SUBPROGRAMS, ENABLE_COMPRESSION, COORDINATE_PRECISION, FEED_PRECISION
        global ENABLE_AUTO_SLICES, DRAFT_MODE, MIN_SLICES, VAR_SCOPE, START_VC
        global ENABLE_SPEEDER, SPEEDER_SCOPE, SPEEDER_DUAL_M00, SPEEDER_VERIFY, SPEEDER_RETRACT_Z
        global SEPARATE_ROUGH_FINISH, ROUGH_SUFFIX, FINISH_SUFFIX

        ENABLE_TOOLCHECK = param_grp.GetBool("EnableToolCheck", ENABLE_TOOLCHECK)
        ENABLE_NATIVE_CYCLES = param_grp.GetBool("EnableNativeCycles", ENABLE_NATIVE_CYCLES)
        ENABLE_SUBPROGRAMS = param_grp.GetBool("EnableSubprograms", ENABLE_SUBPROGRAMS)
        ENABLE_AUTO_SLICES = param_grp.GetBool("EnableAutoSlices", ENABLE_AUTO_SLICES)
        DRAFT_MODE = param_grp.GetString("DraftMode", DRAFT_MODE)
        MIN_SLICES = param_grp.GetInt("MinSlices", MIN_SLICES)
        VAR_SCOPE = param_grp.GetString("VarScope", VAR_SCOPE)
        START_VC = param_grp.GetInt("StartVC", START_VC)
        ENABLE_COMPRESSION = param_grp.GetBool("EnableCompression", ENABLE_COMPRESSION)
        COORDINATE_PRECISION = param_grp.GetInt("CoordinatePrecision", COORDINATE_PRECISION)
        FEED_PRECISION = param_grp.GetInt("FeedPrecision", FEED_PRECISION)

        ENABLE_SPEEDER = param_grp.GetBool("EnableSpeeder", ENABLE_SPEEDER)
        scope_str = param_grp.GetString("SpeederScope", "Finishing Operations Only")
        if "all" in scope_str.lower():
            SPEEDER_SCOPE = "all"
        elif "rough" in scope_str.lower():
            SPEEDER_SCOPE = "rough"
        else:
            SPEEDER_SCOPE = "finish"
        SPEEDER_DUAL_M00 = param_grp.GetBool("SpeederDualM00", SPEEDER_DUAL_M00)
        SPEEDER_VERIFY = param_grp.GetBool("SpeederVerify", SPEEDER_VERIFY)
        SPEEDER_RETRACT_Z = param_grp.GetFloat("SpeederRetractZ", SPEEDER_RETRACT_Z)

        SEPARATE_ROUGH_FINISH = param_grp.GetBool("SeparateRoughFinish", SEPARATE_ROUGH_FINISH)
        ROUGH_SUFFIX = param_grp.GetString("RoughSuffix", ROUGH_SUFFIX)
        FINISH_SUFFIX = param_grp.GetString("FinishSuffix", FINISH_SUFFIX)
    except Exception:
        pass


def reset_defaults() -> None:
    """Reset configuration to initial defaults."""
    global OUTPUT_HEADER, OUTPUT_COMMENTS, OUTPUT_LINE_NUMBERS, ENABLE_MODAL
    global ENABLE_TOOLCHECK, ENABLE_NATIVE_CYCLES, ENABLE_SUBPROGRAMS, ENABLE_COMPRESSION
    global ENABLE_AUTO_SLICES, DRAFT_MODE, MIN_SLICES, VAR_SCOPE, START_VC
    global COORDINATE_PRECISION, FEED_PRECISION, UNITS, UNIT_FORMAT, UNIT_SPEED_FORMAT
    global ENABLE_SPEEDER, SPEEDER_SCOPE, SPEEDER_DUAL_M00, SPEEDER_VERIFY, SPEEDER_RETRACT_Z
    global SEPARATE_ROUGH_FINISH, ROUGH_SUFFIX, FINISH_SUFFIX

    OUTPUT_HEADER = True
    OUTPUT_COMMENTS = True
    OUTPUT_LINE_NUMBERS = False
    ENABLE_MODAL = True
    ENABLE_TOOLCHECK = False
    ENABLE_NATIVE_CYCLES = True
    ENABLE_SUBPROGRAMS = False
    ENABLE_AUTO_SLICES = True
    DRAFT_MODE = "scale"
    MIN_SLICES = 3
    VAR_SCOPE = "local"
    START_VC = 33
    ENABLE_COMPRESSION = True
    COORDINATE_PRECISION = 4
    FEED_PRECISION = 1
    UNITS = "G21"
    UNIT_FORMAT = "mm"
    UNIT_SPEED_FORMAT = "mm/min"

    ENABLE_SPEEDER = False
    SPEEDER_SCOPE = "finish"
    SPEEDER_DUAL_M00 = True
    SPEEDER_VERIFY = True
    SPEEDER_RETRACT_Z = 200.0

    SEPARATE_ROUGH_FINISH = False
    ROUGH_SUFFIX = "_ROUGH"
    FINISH_SUFFIX = "_FINISH"


def processArguments(argstring: str) -> None:
    """Parse CLI argument string passed during post-processing."""
    global OUTPUT_HEADER, OUTPUT_COMMENTS, OUTPUT_LINE_NUMBERS, ENABLE_MODAL
    global ENABLE_TOOLCHECK, ENABLE_NATIVE_CYCLES, ENABLE_SUBPROGRAMS, ENABLE_COMPRESSION
    global ENABLE_AUTO_SLICES, DRAFT_MODE, MIN_SLICES, VAR_SCOPE, START_VC
    global COORDINATE_PRECISION, FEED_PRECISION, UNITS, UNIT_FORMAT, UNIT_SPEED_FORMAT
    global ENABLE_SPEEDER, SPEEDER_SCOPE, SPEEDER_DUAL_M00, SPEEDER_VERIFY, SPEEDER_RETRACT_Z
    global SEPARATE_ROUGH_FINISH, ROUGH_SUFFIX, FINISH_SUFFIX

    reset_defaults()
    load_user_preferences()

    if not argstring:
        return


    for arg in argstring.split():
        arg_clean = arg.strip()
        arg_lower = arg_clean.lower()
        if arg_lower == "--header":
            OUTPUT_HEADER = True
        elif arg_lower == "--no-header":
            OUTPUT_HEADER = False
        elif arg_lower == "--comments":
            OUTPUT_COMMENTS = True
        elif arg_lower == "--no-comments":
            OUTPUT_COMMENTS = False
        elif arg_lower == "--line-numbers":
            OUTPUT_LINE_NUMBERS = True
        elif arg_lower == "--no-line-numbers":
            OUTPUT_LINE_NUMBERS = False
        elif arg_lower == "--modal":
            ENABLE_MODAL = True
        elif arg_lower == "--no-modal":
            ENABLE_MODAL = False
        elif arg_lower == "--toolcheck":
            ENABLE_TOOLCHECK = True
        elif arg_lower == "--no-toolcheck":
            ENABLE_TOOLCHECK = False
        elif arg_lower == "--native-cycles":
            ENABLE_NATIVE_CYCLES = True
        elif arg_lower == "--no-native-cycles":
            ENABLE_NATIVE_CYCLES = False
        elif arg_lower == "--subprograms":
            ENABLE_SUBPROGRAMS = True
        elif arg_lower == "--no-subprograms":
            ENABLE_SUBPROGRAMS = False
        elif arg_lower == "--auto-slices":
            ENABLE_AUTO_SLICES = True
        elif arg_lower == "--no-auto-slices":
            ENABLE_AUTO_SLICES = False
        elif arg_lower.startswith("--draft-mode="):
            DRAFT_MODE = arg_clean.split("=")[1].lower()
        elif arg_lower.startswith("--min-slices="):
            try:
                MIN_SLICES = int(arg_clean.split("=")[1])
            except ValueError:
                pass
        elif arg_lower.startswith("--var-scope="):
            VAR_SCOPE = arg_clean.split("=")[1].lower()
        elif arg_lower == "--compress":
            ENABLE_COMPRESSION = True
        elif arg_lower == "--no-compress":
            ENABLE_COMPRESSION = False
        elif arg_lower == "--inches":
            UNITS = "G20"
            UNIT_FORMAT = "in"
            UNIT_SPEED_FORMAT = "in/min"
        elif arg_lower == "--metric":
            UNITS = "G21"
            UNIT_FORMAT = "mm"
            UNIT_SPEED_FORMAT = "mm/min"
        elif arg_lower.startswith("--precision="):
            try:
                COORDINATE_PRECISION = int(arg_clean.split("=")[1])
            except ValueError:
                pass
        elif arg_lower.startswith("--feed-precision="):
            try:
                FEED_PRECISION = int(arg_clean.split("=")[1])
            except ValueError:
                pass
        elif arg_lower == "--speeder":
            ENABLE_SPEEDER = True
        elif arg_lower == "--no-speeder":
            ENABLE_SPEEDER = False
        elif arg_lower.startswith("--speeder-scope="):
            SPEEDER_SCOPE = arg_clean.split("=")[1].lower()
        elif arg_lower == "--speeder-dual-m00":
            SPEEDER_DUAL_M00 = True
        elif arg_lower == "--no-speeder-dual-m00":
            SPEEDER_DUAL_M00 = False
        elif arg_lower == "--speeder-verify":
            SPEEDER_VERIFY = True
        elif arg_lower == "--no-speeder-verify":
            SPEEDER_VERIFY = False
        elif arg_lower.startswith("--speeder-retract="):
            try:
                SPEEDER_RETRACT_Z = float(arg_clean.split("=")[1])
            except ValueError:
                pass
        elif arg_lower == "--separate-rough-finish":
            SEPARATE_ROUGH_FINISH = True
        elif arg_lower == "--no-separate-rough-finish":
            SEPARATE_ROUGH_FINISH = False
        elif arg_lower.startswith("--rough-suffix="):
            ROUGH_SUFFIX = arg_clean.split("=")[1]
        elif arg_lower.startswith("--finish-suffix="):
            FINISH_SUFFIX = arg_clean.split("=")[1]



def convert_feedrate(feed_mms: float) -> float:
    """Convert FreeCAD internal feedrate (mm/s) to target machine units (mm/min or IPM).

    Uses FreeCAD.Units.Quantity to ensure accurate, non-hardcoded conversions.
    """
    try:
        q = Units.Quantity(f"{feed_mms} mm/s")
        val = q.getValueAs(UNIT_SPEED_FORMAT)
        return float(val)
    except Exception:
        # Fallback if Units subsystem fails
        if UNIT_SPEED_FORMAT == "in/min":
            return (feed_mms * 60.0) / 25.4
        return feed_mms * 60.0


def extract_hole_coordinates(op_obj: Any) -> List[Tuple[float, float, float]]:
    """Extract list of (X, Y, Z) hole positions from a drilling operation."""
    holes = []
    if not hasattr(op_obj, "Path"):
        return holes

    path = PathUtils.getPathWithPlacement(op_obj)
    for cmd in path.Commands:
        if cmd.Name in ("G81", "G82", "G83", "G84", "G85", "G0", "G1"):
            params = cmd.Parameters
            if "X" in params and "Y" in params:
                z = params.get("Z", 0.0)
                holes.append((params["X"], params["Y"], z))
    return holes


def process_speeder_header(dual_m00: bool = True) -> List[str]:
    """Generates the dual-M00 orientation and speeder loading header."""
    lines = [
        "(--------------------------------------------------)",
        "(FEATURE: ELECTRIC SPINDLE SPEEDER SETUP)",
        "(--------------------------------------------------)",
        "G90 G94",
        "M05",
    ]
    if dual_m00:
        lines.extend([
            "(MSG, READY FOR SPINDLE ORIENTATION - PRESS CYCLE START)",
            "M00",
        ])
    lines.extend([
        "M19",
        "(MSG, LOAD SPEEDER NOW & ENGAGE TORQUE ARM - PRESS CYCLE START)",
        "M00",
        "M130",
        "(--------------------------------------------------)",
    ])
    return lines


def process_speeder_cleanup(retract_z: float = 200.0, precision: int = 4) -> List[str]:
    """Generates speeder interlock restoration and removal cleanup."""
    return [
        "(--------------------------------------------------)",
        "(RESTORE MACHINE INTERLOCKS & REMOVE SPEEDER)",
        "(--------------------------------------------------)",
        f"G00 Z{GCodeCompressor.format_number(retract_z, precision)}",
        "M131",
        "(MSG, REMOVE ELECTRIC SPEEDER FROM SPINDLE)",
        "M00",
        "M02",
    ]


def verify_no_spindle_movement_after_speeder_load(gcode_blocks: Sequence[str], dual_m00: bool = True) -> bool:
    """Verifies that no main spindle movement (M03, M04, S-codes, M06, G111, G95)
    occurs after the speeder load point (second M00, or first M00 if single M00).
    """
    speeder_loaded = False
    m00_count = 0

    for line_num, block in enumerate(gcode_blocks, start=1):
        clean_block = block.split('(')[0].strip().upper()  # Ignore comments
        tokens = clean_block.split()

        # Track M00 occurrences in setup header
        if "M00" in tokens or "M0" in tokens:
            m00_count += 1
            if dual_m00 and m00_count >= 2:
                speeder_loaded = True
                continue
            elif not dual_m00 and m00_count >= 1:
                speeder_loaded = True
                continue

        if speeder_loaded:
            # Check for M03 / M04
            if any(m in tokens for m in ["M03", "M3", "M04", "M4"]):
                raise SpeederPostError(
                    f"CRITICAL SAFETY ERROR Line {line_num}: "
                    f"Spindle start command detected after speeder load! Block: '{block}'"
                )
            # Check for S-codes (spindle RPM > 0)
            for token in tokens:
                if token.startswith('S') and len(token) > 1:
                    s_val_str = token[1:].lstrip('=').split('.')[0]
                    if s_val_str.isdigit() and int(s_val_str) > 0:
                        raise SpeederPostError(
                            f"CRITICAL SAFETY ERROR Line {line_num}: "
                            f"Spindle speed S > 0 detected after speeder load! Block: '{block}'"
                        )
            # Check for Tool Change M06 / G111
            if any(m in tokens for m in ["M06", "M6", "G111"]):
                raise SpeederPostError(
                    f"CRITICAL SAFETY ERROR Line {line_num}: "
                    f"Automatic tool change detected during speeder operation! Block: '{block}'"
                )
            # Check for G95 (Feed per Rev forbidden with stationary spindle)
            if "G95" in tokens:
                raise SpeederPostError(
                    f"CRITICAL SAFETY ERROR Line {line_num}: "
                    f"Feed-per-revolution G95 detected during speeder operation! Must use G94. Block: '{block}'"
                )

    return True


def is_finishing_op(op: Any) -> bool:
    """Check if an operation is classified as a finishing operation."""
    op_proxy = getattr(op, "Proxy", None)
    op_type = getattr(op_proxy, "Type", "") if op_proxy else ""
    if not op_type:
        op_type = getattr(op, "Name", "")
    op_name = (getattr(op, "Label", "") or getattr(op, "Name", "")).lower()

    if "finish" in op_name or "finishing" in op_name:
        return True
    if getattr(op, "Purpose", "") == "Finish":
        return True
    return False


def _generate_program_blocks(
    ops_to_process: Sequence[Any],
    prog_num: int,
    stage: str,  # "all", "rough", "finish"
    speeder_mode_active: bool,
    sub_mgr: SubprogramManager,
    optimizer: OptimizerEngine,
    pattern_rec: PatternRecognizer,
) -> Tuple[List[str], bool]:
    """Generate G-code blocks for a given stage of operations."""
    main_lines: List[str] = []

    # 1. Program Header
    main_lines.append(f"O{prog_num:04d}")
    if OUTPUT_HEADER:
        main_lines.append("(==================================================)")
        main_lines.append("( OKUMA OSP CAM POST-PROCESSOR )")
        main_lines.append(f"( DATE: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} )")
        main_lines.append(f"( UNITS: {UNIT_FORMAT.upper()} - {UNITS} )")
        if stage != "all":
            main_lines.append(f"( PROGRAM STAGE: {stage.upper()} )")
        if speeder_mode_active:
            main_lines.append("( ELECTRIC SPINDLE SPEEDER: ACTIVE (STATIONARY SPINDLE) )")
        main_lines.append(f"( TOOLCHECK (OTCHK): {'ENABLED (G111)' if ENABLE_TOOLCHECK else 'DISABLED'} )")
        main_lines.append(f"( NATIVE CYCLES: {'ENABLED' if ENABLE_NATIVE_CYCLES else 'DISABLED'} )")
        main_lines.append(f"( SUBPROGRAMS: {'ENABLED' if ENABLE_SUBPROGRAMS else 'DISABLED'} )")
        main_lines.append("(==================================================)")

    speeder_loaded_in_prog = speeder_mode_active

    if speeder_mode_active:
        main_lines.extend(process_speeder_header(dual_m00=SPEEDER_DUAL_M00))
        main_lines.append(f"{UNITS} G17 G90 G80 G40")
        main_lines.append(WORK_FIXTURE)
    else:
        main_lines.append(f"{UNITS} G17 G90 G80 G40")
        main_lines.append(WORK_FIXTURE)

    current_tool: Optional[int] = None
    active_feedrate: Optional[float] = None
    tool_sequence_idx = 1

    # Filter operations for tool sequence lookahead
    tool_sequence: List[int] = []
    last_scanned_t: Optional[int] = None
    for op in ops_to_process:
        tools_in_op = []
        tc_rough = getattr(op, "RoughingTool", None) or getattr(op, "ToolController", None)
        tc_finish = getattr(op, "FinishingTool", None)
        enable_finish = getattr(op, "EnableFinishing", False)

        if stage in ("all", "rough"):
            if tc_rough and hasattr(tc_rough, "ToolNumber"):
                tools_in_op.append(int(tc_rough.ToolNumber))
            elif hasattr(op, "ToolController") and op.ToolController and hasattr(op.ToolController, "ToolNumber"):
                tools_in_op.append(int(op.ToolController.ToolNumber))

        if stage in ("all", "finish"):
            if enable_finish and tc_finish and hasattr(tc_finish, "ToolNumber"):
                tools_in_op.append(int(tc_finish.ToolNumber))
            elif stage == "finish" and not tools_in_op:
                if tc_finish and hasattr(tc_finish, "ToolNumber"):
                    tools_in_op.append(int(tc_finish.ToolNumber))
                elif hasattr(op, "ToolController") and op.ToolController and hasattr(op.ToolController, "ToolNumber"):
                    tools_in_op.append(int(op.ToolController.ToolNumber))

        for t_num in tools_in_op:
            if t_num != last_scanned_t:
                tool_sequence.append(t_num)
                last_scanned_t = t_num

    def get_next_tool_in_sequence(curr_t: int) -> Optional[int]:
        found_curr = False
        for t in tool_sequence:
            if found_curr:
                return t
            if t == curr_t:
                found_curr = True
        return None

    def emit_standard_tool_change(target_tool: int, next_staged: Optional[int] = None, tc_obj: Any = None) -> None:
        nonlocal current_tool, tool_sequence_idx
        if current_tool == target_tool:
            return
        current_tool = target_tool
        main_lines.append(f"NAT{tool_sequence_idx:02d}")
        main_lines.append(f"T{current_tool} M6")
        main_lines.append(WORK_FIXTURE)
        main_lines.append(f"G56 H{current_tool}")

        if ENABLE_TOOLCHECK:
            if next_staged is not None:
                main_lines.append(f"G111 T{current_tool} Q{next_staged}")
            else:
                main_lines.append(f"G111 T{current_tool}")

        spindle_speed = 1000
        spindle_dir = "M3"
        if tc_obj:
            if hasattr(tc_obj, "SpindleSpeed") and tc_obj.SpindleSpeed > 0:
                spindle_speed = int(tc_obj.SpindleSpeed)
            if hasattr(tc_obj, "SpindleDir") and str(tc_obj.SpindleDir).upper() == "CCW":
                spindle_dir = "M4"
        main_lines.append(f"S{spindle_speed} {spindle_dir}")
        main_lines.append("M8")
        tool_sequence_idx += 1
        optimizer.reset()

    def emit_speeder_tool_change(target_tool: int, tc_obj: Any = None) -> None:
        nonlocal current_tool, tool_sequence_idx, speeder_loaded_in_prog
        if current_tool == target_tool:
            return
        current_tool = target_tool
        if not speeder_loaded_in_prog:
            # Transition from machine spindle to electric speeder
            main_lines.append("M05")
            main_lines.append("G0 Z50.")
            main_lines.extend(process_speeder_header(dual_m00=SPEEDER_DUAL_M00))
            speeder_loaded_in_prog = True
        main_lines.append(WORK_FIXTURE)
        main_lines.append(f"G56 H{current_tool}")
        tool_sequence_idx += 1
        optimizer.reset()

    for op in ops_to_process:
        if not hasattr(op, "Path"):
            continue

        op_proxy = getattr(op, "Proxy", None)
        op_type = getattr(op_proxy, "Type", "") if op_proxy else ""
        if not op_type:
            op_type = getattr(op, "Name", "")

        is_finishing = is_finishing_op(op)

        # Standard operation skipping based on stage
        if op_type not in ("OkumaContourPocket", "OkumaContourSurfacing"):
            if stage == "rough" and is_finishing:
                continue
            if stage == "finish" and not is_finishing:
                continue

        op_name = getattr(op, "Label", getattr(op, "Name", "Op"))
        if OUTPUT_COMMENTS:
            main_lines.append(f"({op_name})")

        handled = False

        # Handler 1: OkumaContourPocket
        if ENABLE_NATIVE_CYCLES and op_type == "OkumaContourPocket":
            tc_rough = getattr(op, "RoughingTool", None) or getattr(op, "ToolController", None)
            tc_finish = getattr(op, "FinishingTool", None) if getattr(op, "EnableFinishing", True) else None

            rough_t = int(tc_rough.ToolNumber) if (tc_rough and hasattr(tc_rough, "ToolNumber")) else (current_tool or 1)
            finish_t = int(tc_finish.ToolNumber) if (tc_finish and hasattr(tc_finish, "ToolNumber")) else None

            def _val(attr_name, default_val):
                v = getattr(op, attr_name, default_val)
                return float(getattr(v, "Value", v))

            start_z = _val("StartDepth", 0.0)
            final_z = _val("FinalDepth", -10.0)
            stepdown = _val("RoughStepDown", 2.0)
            finish_stepdown = _val("FinishStepDown", 1.0)
            stepover = _val("RoughStepOver", 70.0)
            allowance = _val("FinishAllowance", 0.5)

            feed = 250.0
            if tc_rough and hasattr(tc_rough, "HorizFeed"):
                feed = convert_feedrate(float(getattr(tc_rough.HorizFeed, "Value", 4.16)))
            elif hasattr(op, "HorizFeed"):
                feed = convert_feedrate(float(getattr(op.HorizFeed, "Value", 4.16)))

            core_type = getattr(op, "InscribedCoreType", "NONE")
            inscribed_params_str = getattr(op, "InscribedParams", "")
            params_dict = {}
            if inscribed_params_str:
                try:
                    params_dict = json.loads(inscribed_params_str)
                except Exception:
                    pass

            # Roughing pass execution
            if stage in ("all", "rough"):
                staged_for_rough = finish_t if finish_t is not None else get_next_tool_in_sequence(rough_t)
                if speeder_mode_active:
                    emit_speeder_tool_change(rough_t, tc_rough)
                else:
                    emit_standard_tool_change(rough_t, staged_for_rough, tc_rough)

                if core_type == "RECTANGLE" and params_dict:
                    xp = params_dict.get("xp", 0.0)
                    yp = params_dict.get("yp", 0.0)
                    idx = params_dict.get("idx", 50.0)
                    jdy = params_dict.get("jdy", 40.0)

                    cycle_mnemonic = "PMIL" if "Zigzag" in str(getattr(op, "RoughCycle", "")) else "PMILR"
                    if OUTPUT_COMMENTS:
                        main_lines.append(f"( INSCRIBED CORE: RECTANGLE {cycle_mnemonic} )")
                    pmil_line = AreaMachiningEngine.generate_command(
                        mnemonic=cycle_mnemonic,
                        xp=xp,
                        yp=yp,
                        zp=final_z,
                        idx=idx,
                        jdy=jdy,
                        q_stepdown=stepdown,
                        r_rapid_level=start_z + 2.0,
                        k_allowance=allowance,
                        p_stepover_ratio=stepover,
                        d_offset_num=rough_t,
                        feedrate=feed,
                        precision=COORDINATE_PRECISION,
                    )
                    main_lines.append(pmil_line)

                    res_cmds = getattr(op_proxy, "residual_commands", [])
                    if res_cmds:
                        if OUTPUT_COMMENTS:
                            main_lines.append("( RESIDUAL MARGIN ROUGHING )")
                        sub_id = sub_mgr.create_parametric_subprogram(
                            slice_commands=res_cmds,
                            feedrate=feed,
                            precision=COORDINATE_PRECISION,
                        )
                        loop_lines = sub_mgr.generate_parametric_loop(
                            sub_id=sub_id,
                            start_z=start_z,
                            final_z=final_z,
                            stepdown=stepdown,
                            plunge_clearance=2.0,
                            draft_mode="none",
                            var_scope=VAR_SCOPE,
                            start_vc=START_VC,
                            precision=COORDINATE_PRECISION,
                        )
                        main_lines.extend(loop_lines)

                elif core_type == "CIRCLE" and params_dict:
                    xc = params_dict.get("xc", 0.0)
                    yc = params_dict.get("yc", 0.0)
                    radius = params_dict.get("radius", 25.0)

                    if OUTPUT_COMMENTS:
                        main_lines.append("( INSCRIBED CORE: CIRCULAR CYCLE )")
                    circ_line = AreaMachiningEngine.generate_circular_pocket_command(
                        xc=xc,
                        yc=yc,
                        zp=final_z,
                        radius=radius,
                        q_stepdown=stepdown,
                        r_rapid_level=start_z + 2.0,
                        k_allowance=allowance,
                        d_offset_num=rough_t,
                        feedrate=feed,
                        precision=COORDINATE_PRECISION,
                    )
                    main_lines.append(circ_line)

                    res_cmds = getattr(op_proxy, "residual_commands", [])
                    if res_cmds:
                        if OUTPUT_COMMENTS:
                            main_lines.append("( RESIDUAL MARGIN ROUGHING )")
                        sub_id = sub_mgr.create_parametric_subprogram(
                            slice_commands=res_cmds,
                            feedrate=feed,
                            precision=COORDINATE_PRECISION,
                        )
                        loop_lines = sub_mgr.generate_parametric_loop(
                            sub_id=sub_id,
                            start_z=start_z,
                            final_z=final_z,
                            stepdown=stepdown,
                            plunge_clearance=2.0,
                            draft_mode="none",
                            var_scope=VAR_SCOPE,
                            start_vc=START_VC,
                            precision=COORDINATE_PRECISION,
                        )
                        main_lines.extend(loop_lines)

            # Finishing Pass execution
            if stage in ("all", "finish") and finish_t is not None:
                use_speeder_for_finish = speeder_mode_active or (
                    ENABLE_SPEEDER and SPEEDER_SCOPE in ("finish", "all")
                ) or getattr(op, "UseSpeederForFinishing", False)

                if use_speeder_for_finish:
                    emit_speeder_tool_change(finish_t, tc_finish)
                else:
                    staged_for_finish = get_next_tool_in_sequence(finish_t)
                    emit_standard_tool_change(finish_t, staged_for_finish, tc_finish)

                finish_feed = 400.0
                if tc_finish and hasattr(tc_finish, "HorizFeed"):
                    finish_feed = convert_feedrate(float(getattr(tc_finish.HorizFeed, "Value", 6.66)))

                if core_type == "RECTANGLE" and params_dict and "RMILI" in str(getattr(op, "FinishCycle", "RMILI")):
                    xp = params_dict.get("xp", 0.0)
                    yp = params_dict.get("yp", 0.0)
                    idx = params_dict.get("idx", 50.0)
                    jdy = params_dict.get("jdy", 40.0)
                    if OUTPUT_COMMENTS:
                        main_lines.append("( FINISHING PASS: RMILI PERIMETER )")
                    rmili_line = AreaMachiningEngine.generate_command(
                        mnemonic="RMILI",
                        xp=xp,
                        yp=yp,
                        zp=final_z,
                        idx=idx,
                        jdy=jdy,
                        q_stepdown=finish_stepdown,
                        r_rapid_level=start_z + 2.0,
                        k_allowance=0.0,
                        d_offset_num=finish_t,
                        feedrate=finish_feed,
                        precision=COORDINATE_PRECISION,
                    )
                    main_lines.append(rmili_line)

            handled = True

        # Handler 2: OkumaContourSurfacing
        if not handled and ENABLE_NATIVE_CYCLES and op_type == "OkumaContourSurfacing":
            tc_rough = getattr(op, "RoughingTool", None) or getattr(op, "ToolController", None)
            tc_finish = getattr(op, "FinishingTool", None) if getattr(op, "EnableFinishing", True) else None

            rough_t = int(tc_rough.ToolNumber) if (tc_rough and hasattr(tc_rough, "ToolNumber")) else (current_tool or 1)
            finish_t = int(tc_finish.ToolNumber) if (tc_finish and hasattr(tc_finish, "ToolNumber")) else None

            def _val_s(attr_name, default_val):
                v = getattr(op, attr_name, default_val)
                return float(getattr(v, "Value", v))

            start_z = _val_s("StartDepth", 0.0)
            final_z = _val_s("FinalDepth", -5.0)
            stepdown = _val_s("RoughStepDown", 2.0)
            finish_stepdown = _val_s("FinishStepDown", 0.5)
            stepover = _val_s("RoughStepOver", 75.0)
            finish_stepover = _val_s("FinishStepOver", 50.0)
            allowance = _val_s("FinishAllowance", 0.25)

            feed = 250.0
            if tc_rough and hasattr(tc_rough, "HorizFeed"):
                feed = convert_feedrate(float(getattr(tc_rough.HorizFeed, "Value", 4.16)))

            is_planar = getattr(op, "IsPlanarFace", True)
            face_params_str = getattr(op, "FaceParams", "")
            f_dict = {}
            if face_params_str:
                try:
                    f_dict = json.loads(face_params_str)
                except Exception:
                    pass

            xmin = f_dict.get("xmin", 0.0)
            ymin = f_dict.get("ymin", 0.0)
            xlen = f_dict.get("xlen", 100.0)
            ylen = f_dict.get("ylen", 50.0)

            if stage in ("all", "rough") and is_planar:
                staged_for_rough = finish_t if finish_t is not None else get_next_tool_in_sequence(rough_t)
                if speeder_mode_active:
                    emit_speeder_tool_change(rough_t, tc_rough)
                else:
                    emit_standard_tool_change(rough_t, staged_for_rough, tc_rough)

                if OUTPUT_COMMENTS:
                    main_lines.append("( PLANAR SURFACING ROUGHING: FMILR )")
                fmilr_line = AreaMachiningEngine.generate_command(
                    mnemonic="FMILR",
                    xp=xmin,
                    yp=ymin,
                    zp=final_z,
                    idx=xlen,
                    jdy=ylen,
                    q_stepdown=stepdown,
                    r_rapid_level=start_z + 2.0,
                    k_allowance=allowance,
                    p_stepover_ratio=stepover,
                    d_offset_num=rough_t,
                    feedrate=feed,
                    precision=COORDINATE_PRECISION,
                )
                main_lines.append(fmilr_line)

            if stage in ("all", "finish") and finish_t is not None and is_planar:
                use_speeder_for_finish = speeder_mode_active or (
                    ENABLE_SPEEDER and SPEEDER_SCOPE in ("finish", "all")
                ) or getattr(op, "UseSpeederForFinishing", False)

                if use_speeder_for_finish:
                    emit_speeder_tool_change(finish_t, tc_finish)
                else:
                    staged_for_finish = get_next_tool_in_sequence(finish_t)
                    emit_standard_tool_change(finish_t, staged_for_finish, tc_finish)

                finish_feed = 450.0
                if tc_finish and hasattr(tc_finish, "HorizFeed"):
                    finish_feed = convert_feedrate(float(getattr(tc_finish.HorizFeed, "Value", 7.5)))

                if OUTPUT_COMMENTS:
                    main_lines.append("( PLANAR SURFACING FINISHING: FMILF )")
                fmilf_line = AreaMachiningEngine.generate_command(
                    mnemonic="FMILF",
                    xp=xmin,
                    yp=ymin,
                    zp=final_z,
                    idx=xlen,
                    jdy=ylen,
                    k_allowance=0.0,
                    p_stepover_ratio=finish_stepover,
                    r_rapid_level=start_z + 2.0,
                    d_offset_num=finish_t,
                    feedrate=finish_feed,
                    precision=COORDINATE_PRECISION,
                )
                main_lines.append(fmilf_line)

            handled = True

        # Standard tool change for legacy/standard operations
        if not handled:
            tool_id = None
            if hasattr(op, "ToolController") and op.ToolController:
                tc = op.ToolController
                if hasattr(tc, "ToolNumber"):
                    tool_id = int(tc.ToolNumber)

            if tool_id is not None and tool_id != current_tool:
                if speeder_mode_active:
                    emit_speeder_tool_change(tool_id, op.ToolController if hasattr(op, "ToolController") else None)
                else:
                    next_tool = get_next_tool_in_sequence(tool_id)
                    emit_standard_tool_change(tool_id, next_tool, op.ToolController if hasattr(op, "ToolController") else None)

        if ENABLE_NATIVE_CYCLES and ("Face" in op_type or "Facing" in op_name):
            # Attempt to map to FMILR / FMILF
            if hasattr(op, "Shape") and hasattr(op.Shape, "BoundBox"):
                bb = op.Shape.BoundBox
                xp = bb.XMin
                yp = bb.YMin
                idx = bb.XLength
                jdy = bb.YLength
                zp = bb.ZMin
                stepdown = getattr(op, "StepDown", None)
                if stepdown is not None and hasattr(stepdown, "Value"):
                    stepdown = float(stepdown.Value)
                else:
                    stepdown = 2.0

                feed = 250.0
                if hasattr(op, "HorizFeed"):
                    raw_feed = float(getattr(op.HorizFeed, "Value", 4.16))
                    feed = convert_feedrate(raw_feed)

                fmil_line = AreaMachiningEngine.generate_command(
                    mnemonic="FMILR",
                    xp=xp,
                    yp=yp,
                    zp=zp,
                    idx=idx,
                    jdy=jdy,
                    q_stepdown=stepdown,
                    r_rapid_level=bb.ZMax + 2.0,
                    p_stepover_ratio=getattr(op, "StepOver", 70.0),
                    d_offset_num=current_tool if current_tool else 1,
                    feedrate=feed,
                    precision=COORDINATE_PRECISION,
                )
                main_lines.append(fmil_line)
                handled = True

        # Check for Native Hole Patterns (BHC / GRDX / LAA)
        if not handled and ENABLE_NATIVE_CYCLES and ("Drill" in op_type or "Drilling" in op_name):
            hole_coords = extract_hole_coordinates(op)
            if len(hole_coords) >= 3:
                xy_points = [(x, y) for x, y, _ in hole_coords]
                pattern_line = None

                # Try BHC first
                bhc = pattern_rec.recognize_bolt_hole_circle(xy_points, m52_retract=True, precision=COORDINATE_PRECISION)
                if bhc:
                    pattern_line = bhc
                else:
                    # Try Grid
                    grd = pattern_rec.recognize_grid(xy_points, m52_retract=True, precision=COORDINATE_PRECISION)
                    if grd:
                        pattern_line = grd
                    else:
                        # Try Line at Angle
                        laa = pattern_rec.recognize_line_at_angle(xy_points, m52_retract=True, precision=COORDINATE_PRECISION)
                        if laa:
                            pattern_line = laa

                if pattern_line:
                    first_cmd = None
                    path = PathUtils.getPathWithPlacement(op)
                    for c in path.Commands:
                        if c.Name in ("G81", "G82", "G83", "G84", "G85"):
                            first_cmd = c
                            break

                    drill_cycle = "G81"
                    r_level = 2.0
                    z_depth = -10.0
                    feed = 100.0
                    if first_cmd:
                        drill_cycle = first_cmd.Name
                        r_level = first_cmd.Parameters.get("R", 2.0)
                        z_depth = first_cmd.Parameters.get("Z", -10.0)
                        if "F" in first_cmd.Parameters:
                            feed = convert_feedrate(first_cmd.Parameters["F"])

                    cycle_header = f"{drill_cycle} Z{GCodeCompressor.format_number(z_depth, COORDINATE_PRECISION)} R{GCodeCompressor.format_number(r_level, COORDINATE_PRECISION)} F{GCodeCompressor.format_number(feed, FEED_PRECISION)}"
                    main_lines.append(cycle_header)
                    main_lines.append(pattern_line)
                    main_lines.append("G80")
                    handled = True

        # Check for Z-Slice Subprogram Extraction for Pockets & Clearing Operations
        if not handled and (ENABLE_SUBPROGRAMS or ENABLE_AUTO_SLICES):
            path = PathUtils.getPathWithPlacement(op)
            segmenter = ZSliceSegmenter(z_tolerance=1e-3, min_commands_per_slice=3)
            converted_cmds = []
            for c in path.Commands:
                p_copy = dict(c.Parameters)
                if "F" in p_copy:
                    p_copy["F"] = convert_feedrate(p_copy["F"])
                converted_cmds.append((c.Name, p_copy))

            slices = segmenter.segment(converted_cmds)
            if len(slices) >= MIN_SLICES:
                classifier = SliceSimilarityClassifier(tolerance=1e-3)
                classification, meta = classifier.classify(slices, min_slices=MIN_SLICES)

                op_draft = None
                for prop in ("DraftAngle", "TaperAngle", "Draft"):
                    if hasattr(op, prop):
                        val = getattr(op, prop)
                        try:
                            op_draft = float(getattr(val, "Value", val))
                            break
                        except Exception:
                            pass

                if classification == "IDENTICAL" and not op_draft:
                    ref_slice = slices[0]
                    sub_id = sub_mgr.create_parametric_subprogram(
                        slice_commands=ref_slice.commands,
                        feedrate=active_feedrate or 250.0,
                        precision=COORDINATE_PRECISION,
                    )
                    loop_lines = sub_mgr.generate_parametric_loop(
                        sub_id=sub_id,
                        start_z=meta["start_z"],
                        final_z=meta["final_z"],
                        stepdown=meta["stepdown"],
                        plunge_clearance=2.0,
                        draft_mode="none",
                        var_scope=VAR_SCOPE,
                        start_vc=START_VC,
                        precision=COORDINATE_PRECISION,
                    )
                    main_lines.extend(loop_lines)
                    handled = True

                elif classification == "DRAFTED_SCALED" or op_draft:
                    ref_slice = slices[0]
                    sub_id = sub_mgr.create_parametric_subprogram(
                        slice_commands=ref_slice.commands,
                        feedrate=active_feedrate or 250.0,
                        precision=COORDINATE_PRECISION,
                    )
                    effective_draft_mode = DRAFT_MODE if DRAFT_MODE in ("scale", "offset") else "scale"
                    scale_step = meta.get("scale_step", 0.05)
                    centroid = meta.get("centroid", (ref_slice.center_x, ref_slice.center_y))
                    stepdown = meta.get("stepdown", 2.0)
                    start_z = meta.get("start_z", slices[0].depth + stepdown)
                    final_z = meta.get("final_z", slices[-1].depth)

                    draft_ang = op_draft if op_draft is not None else meta.get("draft_angle", 5.0)
                    offset_delta = stepdown * math.tan(math.radians(draft_ang))

                    loop_lines = sub_mgr.generate_parametric_loop(
                        sub_id=sub_id,
                        start_z=start_z,
                        final_z=final_z,
                        stepdown=stepdown,
                        plunge_clearance=2.0,
                        draft_mode=effective_draft_mode,
                        centroid=centroid,
                        scale_start=1.0,
                        scale_step=scale_step,
                        offset_start=0.0,
                        offset_step=offset_delta,
                        var_scope=VAR_SCOPE,
                        start_vc=START_VC,
                        precision=COORDINATE_PRECISION,
                    )
                    main_lines.extend(loop_lines)
                    handled = True

        # Standard Toolpath / Subprogram Parsing
        if not handled:
            path = PathUtils.getPathWithPlacement(op)
            op_lines = []

            for cmd in path.Commands:
                cname = cmd.Name.upper()
                params = cmd.Parameters

                if cname.startswith("(") or cname.startswith(";"):
                    if OUTPUT_COMMENTS:
                        op_lines.append(cname)
                    continue

                if cname in ("G0", "G00", "G1", "G01", "G2", "G02", "G3", "G03"):
                    axes = {}
                    for ax in ("X", "Y", "Z", "A", "B", "C", "I", "J", "K"):
                        if ax in params:
                            axes[ax] = params[ax]

                    feed = None
                    if "F" in params:
                        feed = convert_feedrate(params["F"])

                    block = optimizer.optimize_block(
                        motion=cname,
                        axes=axes,
                        feedrate=feed,
                        force_motion=not ENABLE_MODAL,
                    )
                    if block:
                        op_lines.append(block)
                elif cname in ("G80", "G81", "G82", "G83", "G84", "G85"):
                    tokens = [cname]
                    for p_key, p_val in sorted(params.items()):
                        if p_key == "F":
                            tokens.append(f"F{GCodeCompressor.format_number(convert_feedrate(p_val), FEED_PRECISION)}")
                        else:
                            tokens.append(f"{p_key}{GCodeCompressor.format_number(p_val, COORDINATE_PRECISION)}")
                    op_lines.append(" ".join(tokens))
                elif cname.startswith("M"):
                    op_lines.append(GCodeCompressor.abbreviate_code(cname))
                else:
                    tokens = [cname]
                    for p_key, p_val in sorted(params.items()):
                        tokens.append(f"{p_key}{GCodeCompressor.format_number(p_val, COORDINATE_PRECISION)}")
                    op_lines.append(" ".join(tokens))

            if ENABLE_SUBPROGRAMS and ("Profile" in op_name or "Contour" in op_name):
                sub_id = sub_mgr.create_subprogram(op_lines)
                main_lines.append(f"CALL O{sub_id:04d}")
            else:
                main_lines.extend(op_lines)

    # 3. Postamble / Safety Shutdown
    main_lines.append("G80")
    main_lines.append("M9")
    if speeder_loaded_in_prog:
        main_lines.extend(process_speeder_cleanup(retract_z=SPEEDER_RETRACT_Z, precision=COORDINATE_PRECISION))
    else:
        main_lines.append("M5")
        main_lines.append("G0 Z50.")
        main_lines.append("M02")

    # Apply line numbers if enabled
    if OUTPUT_LINE_NUMBERS:
        numbered = []
        line_num = 10
        for ln in main_lines:
            if ln.startswith("(") or ln.startswith("O") or ln.startswith("N"):
                numbered.append(ln)
            else:
                numbered.append(f"N{line_num} {ln}")
                line_num += 10
        main_lines = numbered

    # Zero spindle movement safety verification
    if speeder_loaded_in_prog and SPEEDER_VERIFY:
        verify_no_spindle_movement_after_speeder_load(main_lines, dual_m00=SPEEDER_DUAL_M00)

    return main_lines, speeder_loaded_in_prog


def export(objectslist: Sequence[Any], filename: str, argstring: str = "") -> PostResult:
    """Export FreeCAD CAM objects to Okuma OSP G-code.

    Supports single combined program export or separate rough/finish program export.
    Returns PostResult supporting (main_code, sub_code) or (rough_code, finish_code).

    Args:
        objectslist: List of FreeCAD CAM objects (Job, Operations, Path Compounds).
        filename: Destination path for main program (.MIN).
        argstring: Command-line arguments.

    Returns:
        PostResult instance (subclass of tuple).
    """
    processArguments(argstring)

    # Deduce active Job and set units
    job_obj = None
    for obj in objectslist:
        if hasattr(obj, "Proxy") and getattr(obj.Proxy, "Type", "") == "Job":
            job_obj = obj
            break

    global UNITS, UNIT_FORMAT, UNIT_SPEED_FORMAT
    if job_obj and hasattr(job_obj, "SetupSheet") and hasattr(job_obj.SetupSheet, "Units"):
        sheet_units = getattr(job_obj.SetupSheet, "Units", "Metric")
        if "inch" in str(sheet_units).lower():
            UNITS = "G20"
            UNIT_FORMAT = "in"
            UNIT_SPEED_FORMAT = "in/min"
        else:
            UNITS = "G21"
            UNIT_FORMAT = "mm"
            UNIT_SPEED_FORMAT = "mm/min"

    prog_num = PROGRAM_NUMBER
    if filename and filename != "-":
        base_name = os.path.splitext(os.path.basename(filename))[0]
        digits = "".join(filter(str.isdigit, base_name))
        if digits:
            prog_num = int(digits[:4])

    # Flatten operation list
    ops_to_process = []
    for item in objectslist:
        if hasattr(item, "Group"):
            ops_to_process.extend(item.Group)
        else:
            ops_to_process.append(item)

    written_files = []

    if SEPARATE_ROUGH_FINISH:
        # 1. Roughing program
        rough_sub_mgr = SubprogramManager(start_sub_id=100)
        rough_optimizer = OptimizerEngine(
            precision=COORDINATE_PRECISION,
            strip_whitespace=ENABLE_COMPRESSION,
            enable_modal=ENABLE_MODAL,
            enable_patterns=ENABLE_NATIVE_CYCLES,
            enable_area_machining=ENABLE_NATIVE_CYCLES,
        )
        rough_pattern_rec = PatternRecognizer(tolerance=1e-3)
        rough_speeder = ENABLE_SPEEDER and SPEEDER_SCOPE in ("rough", "all")

        rough_lines, _ = _generate_program_blocks(
            ops_to_process=ops_to_process,
            prog_num=prog_num,
            stage="rough",
            speeder_mode_active=rough_speeder,
            sub_mgr=rough_sub_mgr,
            optimizer=rough_optimizer,
            pattern_rec=rough_pattern_rec,
        )
        rough_main_gcode = "\n".join(rough_lines) + "\n"
        rough_sub_gcode = None
        if rough_sub_mgr.subprograms:
            sub_blocks = [rough_sub_mgr.generate_sub_file_content(sid) for sid in sorted(rough_sub_mgr.subprograms.keys())]
            rough_sub_gcode = "\n".join(sub_blocks)

        # 2. Finishing program
        finish_sub_mgr = SubprogramManager(start_sub_id=200)
        finish_optimizer = OptimizerEngine(
            precision=COORDINATE_PRECISION,
            strip_whitespace=ENABLE_COMPRESSION,
            enable_modal=ENABLE_MODAL,
            enable_patterns=ENABLE_NATIVE_CYCLES,
            enable_area_machining=ENABLE_NATIVE_CYCLES,
        )
        finish_pattern_rec = PatternRecognizer(tolerance=1e-3)
        finish_speeder = ENABLE_SPEEDER and SPEEDER_SCOPE in ("finish", "all")

        finish_lines, _ = _generate_program_blocks(
            ops_to_process=ops_to_process,
            prog_num=prog_num + 1,
            stage="finish",
            speeder_mode_active=finish_speeder,
            sub_mgr=finish_sub_mgr,
            optimizer=finish_optimizer,
            pattern_rec=finish_pattern_rec,
        )
        finish_main_gcode = "\n".join(finish_lines) + "\n"
        finish_sub_gcode = None
        if finish_sub_mgr.subprograms:
            sub_blocks = [finish_sub_mgr.generate_sub_file_content(sid) for sid in sorted(finish_sub_mgr.subprograms.keys())]
            finish_sub_gcode = "\n".join(sub_blocks)

        # Write separate files to disk
        if filename and filename != "-":
            out_dir = os.path.dirname(filename)
            if out_dir and not os.path.exists(out_dir):
                os.makedirs(out_dir, exist_ok=True)

            base_path, ext = os.path.splitext(filename)
            ext = ext or ".MIN"

            rough_file = f"{base_path}{ROUGH_SUFFIX}{ext}"
            with open(rough_file, "w", encoding="utf-8") as f:
                f.write(rough_main_gcode)
            written_files.append(rough_file)

            if rough_sub_gcode:
                rough_sub_file = f"{base_path}{ROUGH_SUFFIX}.SUB"
                with open(rough_sub_file, "w", encoding="utf-8") as f:
                    f.write(rough_sub_gcode)
                written_files.append(rough_sub_file)

            finish_file = f"{base_path}{FINISH_SUFFIX}{ext}"
            with open(finish_file, "w", encoding="utf-8") as f:
                f.write(finish_main_gcode)
            written_files.append(finish_file)

            if finish_sub_gcode:
                finish_sub_file = f"{base_path}{FINISH_SUFFIX}.SUB"
                with open(finish_sub_file, "w", encoding="utf-8") as f:
                    f.write(finish_sub_gcode)
                written_files.append(finish_sub_file)

        return PostResult(
            first_item=rough_main_gcode,
            second_item=finish_main_gcode,
            rough_main=rough_main_gcode,
            finish_main=finish_main_gcode,
            rough_sub=rough_sub_gcode,
            finish_sub=finish_sub_gcode,
            files_written=written_files,
        )

    else:
        # Standard combined program
        sub_mgr = SubprogramManager(start_sub_id=100)
        optimizer = OptimizerEngine(
            precision=COORDINATE_PRECISION,
            strip_whitespace=ENABLE_COMPRESSION,
            enable_modal=ENABLE_MODAL,
            enable_patterns=ENABLE_NATIVE_CYCLES,
            enable_area_machining=ENABLE_NATIVE_CYCLES,
        )
        pattern_rec = PatternRecognizer(tolerance=1e-3)
        speeder_active = ENABLE_SPEEDER and SPEEDER_SCOPE == "all"

        main_lines, _ = _generate_program_blocks(
            ops_to_process=ops_to_process,
            prog_num=prog_num,
            stage="all",
            speeder_mode_active=speeder_active,
            sub_mgr=sub_mgr,
            optimizer=optimizer,
            pattern_rec=pattern_rec,
        )

        final_main_gcode = "\n".join(main_lines) + "\n"
        final_sub_gcode = None
        if sub_mgr.subprograms:
            sub_blocks = [sub_mgr.generate_sub_file_content(sid) for sid in sorted(sub_mgr.subprograms.keys())]
            final_sub_gcode = "\n".join(sub_blocks)

        if filename and filename != "-":
            out_dir = os.path.dirname(filename)
            if out_dir and not os.path.exists(out_dir):
                os.makedirs(out_dir, exist_ok=True)

            with open(filename, "w", encoding="utf-8") as f:
                f.write(final_main_gcode)
            written_files.append(filename)

            if final_sub_gcode:
                base, _ = os.path.splitext(filename)
                sub_filename = f"{base}.SUB"
                with open(sub_filename, "w", encoding="utf-8") as f:
                    f.write(final_sub_gcode)
                written_files.append(sub_filename)

        return PostResult(
            first_item=final_main_gcode,
            second_item=final_sub_gcode,
            rough_main=final_main_gcode,
            finish_main=None,
            rough_sub=final_sub_gcode,
            finish_sub=None,
            files_written=written_files,
        )


def parse(pathobj: Any) -> str:
    """Parse a single FreeCAD CAM Path object into Okuma G-code blocks."""
    lines, _ = export([pathobj], filename="-")
    return lines
