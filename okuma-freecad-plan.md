# Implementation Plan: FreeCAD Okuma OSP CAM Add-On & Post-Processor

## 1. Executive Summary & Goal
The objective is to implement a production-grade FreeCAD CAM (Path) Workbench add-on and post-processor specifically engineered for **Okuma OSP CNC controls** (OSP7000 / OSP-P series: P200, P300, P500).

Target Environment & Configuration:
- **FreeCAD**: Version 1.1.4 (Revision 20260928, headless `FreeCADCmd.exe` and GUI support).
- **GUI Framework**: Pure **PySide6** (FreeCAD 1.1.4 ships with PySide6 6.8.3).
- **Python Runtime**: Python 3.11.14 (embedded conda-forge runtime).
- **Tool Check Macro**: `G111` is dedicated and mapped to the `OTCHK` subprogram saved in `TOOLCHK.LIB`. The post-processor will reserve `G111` exclusively for tool check routines.
- **Reference Specification**: Follows all conventions, cycle formats, and logic defined in `okuma-native-functions-and-user-tasks.md`.

---

## 2. Architecture & File Structure

```
OkumaCAM/
├── package.xml                 # Addon Manager metadata manifest (FreeCAD 1.1 standard)
├── Init.py                     # Headless initialization & post-processor registration
├── InitGui.py                  # PySide6 GUI workbench/command registration
├── OkumaOSP_post.py            # FreeCAD CAM post-processor interface (export & parse)
├── OkumaOptimizer.py           # Core geometry compression, modal engine & Okuma OSP logic
├── Gui/
│   ├── __init__.py
│   ├── Preferences.py          # PySide6 CAM preference settings page
│   └── Resources/              # Add-on icons (SVG / PNG)
│       └── okuma_cam.svg
└── tests/
    ├── __init__.py
    ├── test_compression.py     # Unit tests for low-level G-code formatting & compression
    ├── test_modal.py           # Unit tests for modal state tracking & suppression
    ├── test_area_machining.py  # Unit tests for FMILR/F, PMIL/R, RMILO/I and subprograms
    ├── test_patterns.py        # Unit tests for BHC, GRDX, GRDY, LAA hole patterns
    ├── test_toolchange_macro.py# Unit tests for G111 (OTCHK / TOOLCHK.LIB) and tool calls
    └── test_post_integration.py# Integration tests with FreeCAD Path.Command & Jobs
```

---

## 3. Detailed Component Specifications

### 3.1 `OkumaOptimizer.py` (Core Optimization & Macro Engine)
This module operates headlessly without any GUI dependencies.

1. **Low-Level Character Compression (`GCodeCompressor`)**:
   - Single-digit abbreviation:
     - `G00` → `G0`, `G01` → `G1`, `G02` → `G2`, `G03` → `G3`
     - `M03` → `M3`, `M05` → `M5`, `M08` → `M8`, `M09` → `M9`, `M02` → `M2`, `M30` → `M30`
     - Tool calls: `T01` → `T1`, `H01` → `H1`
   - Numeric formatter (`format_coord`, `format_feed`):
     - Strip leading zeros before decimal: `0.5` → `.5`, `-0.125` → `-.125`
     - Strip trailing zeros: `10.500` → `10.5`, `10.0` → `10.`
     - Strip positive signs: `+12.4` → `12.4`
     - Configurable coordinate precision (default 4 decimal places for metric, 5 for imperial).
   - Whitespace and line number management:
     - Optional stripping of non-essential whitespace.
     - Suppression of `N` numbers except for branching targets (`N100`, etc.).

2. **Modal State Tracker (`ModalTracker`)**:
   - Motion mode tracking (`G0`, `G1`, `G2`, `G3`).
   - Coordinate tracking (`X`, `Y`, `Z`, `A`, `B`, `C`, `I`, `J`, `K`).
   - Active feedrate (`F`), spindle speed (`S`), and spindle state (`M3`, `M4`, `M5`).
   - Work coordinate system tracking (`G15 H1`, etc.).
   - Suppresses unchanged axis coordinates and repeated motion commands.

3. **Pattern Function Generator (`PatternRecognizer`)**:
   - Analyzes hole coordinates from drilling operations and array features:
     - **Bolt Hole Circle (`BHC`)**: Evaluates radial distance from center and angular distribution:
       `BHC Xp_ Yp_ I_ J_ K_` (I: radius, J: start angle, K: hole count; positive=CCW, negative=CW).
     - **Grid Array (`GRDX` / `GRDY`)**: Detects regular row/column pitch and count:
       `GRDX Xp_ Yp_ I±dx J±dy Knx Pny` / `GRDY Xp_ Yp_ I±dx J±dy Knx Pny`.
     - **Line at Angle (`LAA`)**: Detects linear arrays along a constant vector:
       `LAA Xp_ Yp_ I±dist Kcount Jangle`.
     - Supports optional `M52` (retract Z to upper limit after final hole) and `OMIT R_` modifiers.
   - Emits Okuma canned cycles (`G81` drilling, `G82` counterbore/dwell, `G83` deep hole peck, `G84` tapping, `G85` reaming) followed by pattern invocations.

4. **Native Area Machining Engine (`AreaMachiningEngine`)**:
   - Conforms strictly to section 1 of `okuma-native-functions-and-user-tasks.md`:
     `[(Mnemonic)] Xp_ Yp_ Zp_ I±dx J±dy K_ P_ Q_ R_ D_ F_ FA=_ FB=_`
   - **Facing**:
     - `FMILR`: Facing roughing (zigzag on-workpiece)
     - `FMILF`: Facing finishing (parallel off-workpiece strokes)
   - **Pocketing**:
     - `PMIL`: Rectangular zigzag pocketing + perimeter cleanup
     - `PMILR`: Spiral pocketing
   - **Perimeter**:
     - `RMILO`: External perimeter milling
     - `RMILI`: Internal perimeter milling
   - Parameter calculation:
     - `FA=` transition feedrate (default `4 * F`)
     - `FB=` Z infeed feedrate (default `F / 4`)
     - `P` stepover ratio (default `70`)
     - `Q` depth per pass (Z stepdown)
     - `R` rapid return level
     - `K` finish allowance
   - Fallback: Complex non-rectangular geometries automatically fall back to compressed standard G-code lines.

5. **Subprogram & Macro Generator (`SubprogramManager`)**:
   - Multi-pass contour extraction:
     - Detects identical XY profiles repeating across multiple Z stepdowns.
     - Extracts the 2D contour into a `.SUB` file starting with `O<sub_id>` and terminating with `RTS`.
     - Generates a parameter loop in the `.MIN` file using `CALL O<sub_id>` or `MODIN` / `MODOUT` with variable stepping (`VC1 = ...`, `IF [VC1 LE ...] N...`).
   - Macro Syntax:
     - Spaces strictly enforced inside brackets around relational operators (`LT`, `LE`, `EQ`, `NE`, `GT`, `GE`), e.g. `IF [VC1 LE 5] N100`.

---

### 3.2 `OkumaOSP_post.py` (FreeCAD Post-Processor)
Implements FreeCAD's native post-processor interface:

1. **Standard Entry Points**:
   - `export(objectslist, filename, argstring)`:
     - Parses `argstring` for flags (e.g. `--toolcheck`, `--metric`, `--imperial`, `--subprograms`, `--compress`, `--native-cycles`).
     - Resolves the FreeCAD CAM Job object and its operational units (`Job.SetupSheet` / `Quantity`).
     - Converts internal CAM feedrates (`mm/s`) to machine units (`mm/min` or `IPM`) via `FreeCAD.Units`.
     - Orchestrates `OkumaOptimizer` passes.
     - Writes the primary `.MIN` file and (if subprograms are enabled) the associated `.SUB` file.
   - `parse(pathobj)`:
     - Converts individual FreeCAD `Path.Command` lists into optimized Okuma G-code blocks.

2. **Tool Change & Tool Check Routine Integration**:
   - Standard Okuma tool sequence:
     ```gcode
     NAT01
     T1 M6
     G15 H1
     G56 H1
     (Optional Tool Check Macro call:)
     G111 T1 (Calls OTCHK in TOOLCHK.LIB)
     ```
   - `G111` is explicitly reserved for `OTCHK` (`TOOLCHK.LIB`) and never overridden by general user macros.
   - User preference toggle in GUI and `--toolcheck` argument in CLI to enable/disable inserting `G111` tool check blocks.

3. **Okuma OSP Specific Header & Safety Blocks**:
   - Program header: `O<ProgNumber>` (e.g. `O1000`).
   - Fixture offsets: `G15 H1` (Okuma coordinate systems).
   - Tool length compensation: `G56 H<tool>`.
   - Cycle cancellations and program end: `G80`, `M9`, `M5`, `M2` / `M30`.

---

### 3.3 `Gui/Preferences.py` (PySide6 Settings Interface)
Provides a clean, modern preference page in FreeCAD's Preferences dialog under CAM:

1. **Fields & Controls**:
   - Controller Generation dropdown (`OSP7000`, `OSP-P200`, `OSP-P300`, `OSP-P500`).
   - **Tool Check Macro (`G111` / `OTCHK`)**:
     - Checkbox: "Enable G111 Tool Check (OTCHK / TOOLCHK.LIB)"
   - Native Area Machining checkbox (Enable `FMILR`, `PMILR`, `RMILO`).
   - Hole Pattern Recognition checkbox (Enable `BHC`, `GRDX`, `GRDY`, `LAA`).
   - Subprogram Generation checkbox (Separate `.SUB` files for multi-pass contours).
   - Numeric Precision spinboxes (coordinate decimals, feed decimals).
   - Compression Aggressiveness toggles (whitespace stripping, zero suppression, modal suppression).
2. **Persistence**:
   - Uses FreeCAD's `App.ParamGet("User parameter:BaseApp/Preferences/Mod/OkumaCAM")` to save and restore user configuration seamlessly.

---

### 3.4 `Init.py`, `InitGui.py`, and `package.xml`
1. **`Init.py`**:
   - Registers `OkumaOSP_post` into FreeCAD's CAM post-processor directory search path.
2. **`InitGui.py`**:
   - Creates `OkumaCAM` menu and toolbar items.
   - Registers custom `Gui.Command` ("OkumaCAM_ExportJob", "OkumaCAM_Preferences") using PySide6.
3. **`package.xml`**:
   - Conforms to FreeCAD Addon Manager schema, allowing 1-click installation and validation.

---

## 4. Verification & Testing Strategy

### 4.1 Automated Headless Tests (`FreeCADCmd.exe` / FreeCAD Python)
Running tests directly through `C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe` or `python.exe`:

1. **`tests/test_compression.py`**:
   - Tests coordinate stripping: `format_coord(0.5) == ".5"`, `format_coord(-0.25) == "-.25"`, `format_coord(10.0) == "10."`.
   - Tests single-digit command compression: `G00` → `G0`, `M03` → `M3`, `T01` → `T1`.
   - Tests line-length and file-size reduction metrics (>30% reduction on dense toolpaths).

2. **`tests/test_modal.py`**:
   - Tests suppression of consecutive redundant `G1`, `G0`, unchanged `Z`, unchanged `F`.

3. **`tests/test_patterns.py`**:
   - Tests circular hole pattern -> produces `BHC Xp Yp I_ J_ K_`.
   - Tests rectangular hole array -> produces `GRDX` / `GRDY`.
   - Tests angular hole series -> produces `LAA`.

4. **`tests/test_area_machining.py`**:
   - Tests facing toolpaths -> outputs `FMILR` with `I, J, K, P, Q, R, D, F, FA=, FB=`.
   - Tests pocket toolpaths -> outputs `PMIL` / `PMILR`.
   - Tests perimeter toolpaths -> outputs `RMILO` / `RMILI`.
   - Tests multi-depth profile -> outputs `.SUB` subprogram with `RTS` and `CALL`/`MODIN` in main `.MIN`.

5. **`tests/test_toolchange_macro.py`**:
   - Tests tool change block generation with and without `G111` (`OTCHK` in `TOOLCHK.LIB`).
   - Verifies that `G111` is never assigned to other conflicting macro functions.

6. **`tests/test_post_integration.py`**:
   - Creates a synthetic FreeCAD CAM Job in a headless FreeCAD Document.
   - Adds operations (`Path.Op.Face`, `Path.Op.Pocket_Shape`, `Path.Op.Drilling`).
   - Runs `OkumaOSP_post.export()`.
   - Validates generated `.MIN` and `.SUB` syntax and integrity.

7. **`tests/test_gui.py`**:
   - Validates PySide6 UI definitions, widget instantiation, and parameter read/write without crashing.

---

## 5. Implementation Phases & Milestones

1. **Phase 1: Project Scaffolding & Directory Setup**:
   - Create `OkumaCAM/` directory structure, `package.xml`, `Init.py`, `InitGui.py`, and resources.
2. **Phase 2: Core Optimization Engine (`OkumaOptimizer.py`)**:
   - Implement `GCodeCompressor`, `ModalTracker`, `PatternRecognizer`, `AreaMachiningEngine`, and `SubprogramManager`.
3. **Phase 3: Post-Processor Implementation (`OkumaOSP_post.py`)**:
   - Implement `export()`, `parse()`, quantity conversion, argument parsing, `G111` tool check integration, `.MIN` / `.SUB` file writers.
4. **Phase 4: PySide6 GUI & Preferences (`Gui/Preferences.py`)**:
   - Implement preference page and parameter bindings.
5. **Phase 5: Comprehensive Automated Testing**:
   - Write and run unit & integration tests using `FreeCADCmd.exe`. Verify all tests pass.
6. **Phase 6: Final Review & Verification**:
   - Full test run, output verification, and walkthrough generation.
