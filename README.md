# OkumaCAM - Okuma OSP CAM Workbench & Post-Processor for FreeCAD

[![License: LGPL v2.1](https://img.shields.io/badge/License-LGPL_v2.1-blue.svg)](LICENSE)
[![FreeCAD](https://img.shields.io/badge/FreeCAD-v1.0%20%7C%20v1.1-orange.svg)](https://www.freecad.org/)
[![Tests](https://img.shields.io/badge/Tests-93%2F93%20Passing-brightgreen.svg)](run_tests.py)
[![Okuma OSP](https://img.shields.io/badge/Okuma-OSP7000%20%7C%20OSP--P%20Series-red.svg)](https://www.okuma.com/)

**OkumaCAM** is a high-performance, size-optimized CAM workbench extension and post-processor for **FreeCAD**, engineered specifically for **Okuma CNC Machining Centers** running OSP controllers (OSP7000, OSP-E100, OSP-P200, OSP-P300, and OSP-P500).

---

## Why OkumaCAM?

Standard CAM post-processors output vast, bloated point-to-point G-code files containing tens of thousands of lines of `G1` linear segments. On Okuma CNC controls, this leads to memory exhaustion, DNC drip-feed bottlenecks, and lost cycle time.

**OkumaCAM** transforms FreeCAD toolpaths into native Okuma OSP control constructs:
- **Up to 90%+ G-code file size reduction**: Replaces massive waterline toolpaths with single-block native canned cycles (`PMILR`, `FMILR`, `RMILI`, `BHC`, `GRDX`, `LAA`).
- **Parametric Subroutines (`.SUB`)**: Loops identical or drafted Z-slices using local Okuma variables (`LA`, `LB`, `LC`) and Okuma `CALL O...` macros.
- **Inscribed Volume Pocketing**: Automatically identifies internal rectangular and circular core cavities, clearing them with canned cycles while isolating residual corner cusps into tight subprogram routines.
- **Dual-Tool Roughing & Finishing**: Automatically sequences roughing and finishing passes with Okuma ATC lookahead tool-staging (`G111 T<rough> Q<finish>`).
- **Electric Spindle Speeder Support**: Full compliance with stationary main spindle speeder workflows (`M130`/`M131`, `M19` orientation lock, dual `M00` stops, `G94` feed enforcement, and strict zero-movement safety verification).
- **Multi-Program Rough / Finish Export**: Option to partition toolpaths into dedicated `<Part>_ROUGH.MIN` and `<Part>_FINISH.MIN` programs.

---

## Architecture Overview

```
                      CAM Job / Operations
                               │
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
   OkumaContourPocket                   OkumaContourSurfacing
   (Inscribed Volume Detection)         (Planar & Contour Facing)
            │                                     │
            └──────────────────┬──────────────────┘
                               ▼
                   Inscribed Volume Analyzer
                 (MIR Histogram / LIC Quadtree)
                               │
            ┌──────────────────┴──────────────────┐
            ▼ (Coverage >= 50%)                   ▼ (Coverage < 50%)
   Hybrid Canned Cycle Strategy          Waterline Subprogram Strategy
   1. Core Canned Cycle (PMILR/Circ)     1. Multi-depth subprogram loop
   2. Residual Margin Clearing (SUB)        (CALL O... PZ=[LA])
   3. Perimeter Finish (RMILI)           2. Finish contour (RMILI)
                               │
                               ▼
                 OkumaOSP_post Post-Processor
   ┌────────────────────────────────────────────────────────┐
   │ • Single Program or Multi-Program Rough/Finish Split   │
   │ • Tool Check & Lookahead Staging (G111 T_ Q_)          │
   │ • Electric Spindle Speeder Logic (M130 / M19 / G94)    │
   │ • Modal Suppression & G-Code Space Compression         │
   │ • Zero Main Spindle Movement Safety Verification       │
   └────────────────────────────────────────────────────────┘
                               │
                               ▼
            .MIN Main Program + .SUB Subroutine Files
```

---

## Key Features

### 1. Inscribed Volume Core Cavity Clearing
Arbitrary 2.5D and 3D pocket geometries are analyzed in real-time using computational geometry algorithms:
- **Maximum Inscribed Rectangle (MIR)**: Monotonic stack largest-rectangle-in-histogram algorithm ($O(W \times H)$) identifies the largest rectangular block clearable with `PMILR` or `PMIL`.
- **Largest Inscribed Circle (LIC)**: Hierarchical quadtree Pole of Inaccessibility algorithm identifies the maximum circular core clearable with circular pocket canned cycles.
- **Residual Clearing**: Calculates 1D scanline differences ($X_{boundary} \setminus X_{core}$) to machine remaining corner cusps with compact subprograms.

### 2. Dual-Tool Lookahead & ATC Macro Staging
Supports both a primary roughing tool and a dedicated finishing tool in a single operation:
- Emits sequential tool sequence sections (`NAT01`, `NAT02`).
- Stages the next tool in the carousel ahead of time using the Okuma `G111` macro (`G111 T1 Q2`), eliminating tool-change wait times.

### 3. Electric Spindle Speeder Integration
High-speed electric spindle attachments (e.g. 24,000–60,000 RPM motorized attachments) have external power umbilicals and torque arms that require the CNC machine's main spindle to remain completely stationary at 0 RPM:
- **`G90 G94`**: Enforces feed-per-minute mode (prevents spindle-encoder lockup from `G95`).
- **Dual `M00` Stops**: Pre-orientation stop (`M00`), spindle orientation lock (`M19`), followed by speeder loading stop (`M00`).
- **`M130` / `M131`**: Commands `M130` to bypass Okuma spindle interlocks during speeder cutting, and restores them with `M131` during cleanup.
- **Safety Verification**: Automated post-processing verification pass raises `SpeederPostError` if any forbidden commands (`M03`, `M04`, `S > 0`, `M06`, `G111`, `G95`) appear after speeder loading.
- **Speeder Tool Changes**: Omits ATC commands and spindle start blocks, emitting only fixture offsets and `G56 H<tool_num>`.

### 4. Multi-Program Rough / Finish Export
Export roughing and finishing passes into separate programs:
- `<Part>_ROUGH.MIN` (with `<Part>_ROUGH.SUB` if subprograms are enabled).
- `<Part>_FINISH.MIN` (with `<Part>_FINISH.SUB` if subprograms are enabled).
- Allows running roughing on the heavy machine spindle with standard tooling, then swapping to the electric speeder for finishing passes.

### 5. Native Okuma Canned Cycles Supported

| Cycle | Description | Syntax Summary |
| :--- | :--- | :--- |
| **`PMILR`** | Rectangular Pocket Milling (Spiral/Helical) | `PMILR X_ Y_ Z_ I_ J_ K_ Q_ R_ P_ D_ F_` |
| **`PMIL`** | Rectangular Pocket Milling (Zigzag) | `PMIL X_ Y_ Z_ I_ J_ K_ Q_ R_ P_ D_ F_` |
| **`FMILR`** | Rectangular Face Milling (Roughing) | `FMILR X_ Y_ Z_ I_ J_ K_ Q_ R_ P_ D_ F_` |
| **`FMILF`** | Rectangular Face Milling (Finishing) | `FMILF X_ Y_ Z_ I_ J_ K_ Q_ R_ D_ F_` |
| **`RMILI`** | Inside Pocket Perimeter Clean-up | `RMILI X_ Y_ Z_ I_ J_ K_ Q_ R_ D_ F_` |
| **`BHC`** | Bolt Hole Circle Drilling Pattern | `BHC X_ Y_ I_ J_ K_ M52` |
| **`GRDX`** | Grid Array Drilling Pattern | `GRDX X_ Y_ I_ J_ K_ P_ M52` |
| **`LAA`** | Line-at-Angle Drilling Pattern | `LAA X_ Y_ I_ J_ K_ M52` |
| **`G111`** | Okuma Tool Change & Pre-Staging Macro | `G111 T<current> Q<next_tool>` |
| **`M130`/`M131`** | Spindle Interlock Bypass & Restoration | `M130` (Speeder active) / `M131` (Restored) |

---

## Installation

### Manual Installation
1. Locate your FreeCAD User `Mod` directory:
   - **Windows**: `%APPDATA%\FreeCAD\Mod\` (e.g. `C:\Users\<User>\AppData\Roaming\FreeCAD\Mod\`)
   - **Linux**: `~/.local/share/FreeCAD/Mod/`
   - **macOS**: `~/Library/Application Support/FreeCAD/Mod/`
2. Clone this repository into your `Mod` directory:
   ```bash
   git clone https://github.com/LotusXdev/FreeCAD-OkumaCAM.git OkumaCAM
   ```
3. Restart FreeCAD. You will now see **OkumaCAM** in the Workbench selector, as well as **OkumaOSP_post** in the CAM Post-Processor dropdown.

---

## Quick Start Guide

For an in-depth walkthrough with tutorials, see [docs/QUICKSTART.md](docs/QUICKSTART.md).

### 1. Configure Preferences
Open **Edit -> Preferences -> OkumaCAM** (or press **CAM -> Okuma OSP Settings...**):
- Select your controller model (**OSP-P300**, **OSP-P500**, etc.).
- Enable **G111 Tool Check Macro**, **Native Area Machining Cycles**, and **Subprograms**.
- Configure **Electric Spindle Speeder** and **Multi-Program Rough/Finish Export** if applicable.

### 2. Add an Okuma Contour Pocket Operation
1. In the FreeCAD CAM Workbench, select your part's pocket face or geometry.
2. Click **Contour Pocket (Okuma)...** on the OkumaCAM toolbar.
3. In the TaskPanel:
   - Select your **Roughing Tool** (e.g. 1/2" End Mill) and optional **Finishing Tool** (e.g. 1/4" Ball/End Mill).
   - The panel displays live geometry diagnostics: detected area, inscribed core type (`RECTANGLE` or `CIRCLE`), and coverage percentage.
   - Adjust `RoughStepDown`, `FinishStepDown`, and `FinishAllowance`.
   - Check **Use Electric Spindle Speeder for Finishing** if you are running a high-speed spindle attachment.
4. Click **OK**.

### 3. Export Okuma OSP G-Code
1. Select your CAM Job or Operations.
2. Click **CAM -> Export Okuma OSP G-Code...** (or press `Ctrl+Shift+O`).
3. Select the output destination (e.g. `Part1.MIN`).
4. If **Multi-Program Export** is enabled, OkumaCAM automatically generates `Part1_ROUGH.MIN` and `Part1_FINISH.MIN` along with their `.SUB` files.

---

## Command-Line Post-Processing

You can also run the post-processor headlessly from scripts or terminal:

```bash
# Export using standard canned cycles and toolcheck staging
python -m OkumaCAM.OkumaOSP_post --native-cycles --toolcheck job.xml -o Part.MIN

# Export with separate roughing and finishing programs
python -m OkumaCAM.OkumaOSP_post --separate-rough-finish --native-cycles job.xml -o Part.MIN

# Export with Electric Spindle Speeder enabled on finish pass
python -m OkumaCAM.OkumaOSP_post --separate-rough-finish --speeder --speeder-scope=finish job.xml -o Part.MIN
```

### Supported CLI Options
| Flag | Description |
| :--- | :--- |
| `--native-cycles` / `--no-native-cycles` | Enable/disable Okuma `PMILR`, `FMILR`, `RMILI`, `BHC`, etc. |
| `--subprograms` / `--no-subprograms` | Enable/disable separate `.SUB` subprogram file generation. |
| `--toolcheck` / `--no-toolcheck` | Emit `G111 T_ Q_` tool staging blocks. |
| `--speeder` / `--no-speeder` | Enable Electric Spindle Speeder mode (`M130`, stationary spindle). |
| `--speeder-scope=finish\|all\|rough` | Select which operations run with the electric speeder. |
| `--speeder-dual-m00` | Enforce pre-orientation and speeder loading `M00` stops. |
| `--speeder-retract=200.0` | Safe Z height for speeder mounting and removal. |
| `--separate-rough-finish` | Export roughing and finishing passes into separate `.MIN` files. |
| `--rough-suffix=_ROUGH` | Suffix for roughing program file. |
| `--finish-suffix=_FINISH` | Suffix for finishing program file. |
| `--metric` / `--inches` | Metric (`G21`) or Imperial (`G20`) unit mode. |
| `--compress` / `--no-compress` | Enable/disable modal whitespace suppression. |

---

## Testing & Quality Assurance

OkumaCAM includes a comprehensive automated test suite with **93 tests across 13 test suites**, achieving a **100% pass rate** across all environments:

```bash
# Run via pytest (Anaconda, standard Python, CI)
python -m pytest

# Run via FreeCAD embedded Python
python run_tests.py

# Run natively inside FreeCADCmd
FreeCADCmd -c -M "OkumaCAM" -t TestOkumaCAMApp
```

### Verified Test Suites
- `test_electric_speeder.py`: 11 tests verifying dual `M00`, `M19`, `M130`, `G94`, cleanup, and zero-spindle-movement safety assertions.
- `test_separate_rough_finish.py`: 9 tests verifying multi-program rough/finish generation, subprogram partitioning, and cycle separation.
- `test_inscribed_volume.py`: 9 tests verifying MIR raster stack search, LIC quadtree search, and residual margin clearing.
- `test_contour_pocket.py`: 4 integration tests for contour pocketing and hybrid core clearing.
- `test_contour_surfacing.py`: 3 integration tests for planar facing and dual-tool surfacing.
- `test_area_machining.py`: Canned cycle parameter validation (`PMILR`, `FMILR`, `RMILI`).
- `test_patterns.py`: Hole pattern recognizers (`BHC`, `GRDX`, `LAA`).
- `test_zslice_subprograms.py`: Waterline Z-slice segmentation, `G51` coordinate scaling, and tool offset draft loops.
- `test_toolchange_macro.py`: Lookahead pre-staging (`G111 T_ Q_`).
- `test_compression.py`: G-code modal optimization and whitespace suppression.
- `test_modal.py`: Modal tracker state transitions.
- `test_gui.py`: PySide6 Preferences and Operation TaskPanels.
- `test_post_integration.py`: End-to-end FreeCAD CAM job export.

---

## Macro Library (`TOOLCHK.LIB`)

To use OkumaCAM's `G111` tool check and pre-staging functionality on your machine, install the included [`TOOLCHK.LIB`](TOOLCHK.LIB) library into your Okuma OSP control's library directory:

```gcode
OTCHK
( SET GCODE PARAM. G111 TO OTCHK )
( AT TOOL CHANGE KEY IN G111 T= TOOL NO. Q = NEXT TOOL EX: G111 T1 Q2)
IF [ VTLCN EQ PT ]NST1 (ACTIVE TOOL)
IF [ VTLNN EQ PT ]NRT1 (NEXT TOOL)
IF [ VTLNN EQ 0 ]NOT1 (NEXT TOOL)
M64
NOT1 T=PT
NRT1 M06
NST1
IF [ PQ EQ EMPTY ]NEND (IF READY TOOL EMPTY/JUMP )
IF [ VTLNN EQ PQ ]NEND (IF PREP TOOL IS AT NEXT TOOL POS./JUMP)
IF [ VTLNN EQ 0 ]NTT1 (IF NEXT TOOL HAS NO VALUE)
M64 (NEXT TOOL POT RETURN)
NTT1
T=PQ
M356 (NEXT POT ADVANCE)
NEND
G56 H=VTLCN
RTS
```

---

## License

This project is licensed under the **GNU Lesser General Public License v2.1 or later (LGPL-2.1-or-later)** to match FreeCAD standard licensing. See [LICENSE](LICENSE) for full details.

---

## Author & Maintainer

**Nathan Brand** ([LotusXdev](https://github.com/LotusXdev))  
Email: [nathan@lotus-x.com](mailto:nathan@lotus-x.com)  
Repository: [https://github.com/LotusXdev/FreeCAD-OkumaCAM](https://github.com/LotusXdev/FreeCAD-OkumaCAM)
