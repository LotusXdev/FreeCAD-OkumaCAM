# Prompt: FreeCAD Okuma OSP CAM Add-On & Post-Processor Generator

Write a complete, production-ready Python add-on and post-processor module for the FreeCAD CAM (Path) Workbench (`OkumaOSP_post.py` and `OkumaOptimizer.py`). 

The module must intercept FreeCAD toolpaths (`Path.Command` objects and operation properties) and output heavily size-optimized G-code specifically tailored for Okuma OSP controls (such as OSP7000 / OSP-P series).

---

## FREECAD PYTHON MODULE BEST PRACTICES & ARCHITECTURE STANDARDS

1. **Strict App vs. GUI Separation**:
   - **`App` (Headless Core)**: Core logic, post-processing, and path geometric transformations must reside strictly in non-GUI modules (using `import FreeCAD as App`). The post-processor MUST be capable of running in headless batch mode or CLI without requiring `FreeCADGui`.
   - **`Gui` (Interface Layer)**: All Qt/PySide dialogs, task panels, tree view icons, and preference pages must be isolated in GUI initialization routines (using `import FreeCADGui as Gui`) and rendered using `PySide` (PySide2/PySide6 compatible).

2. **Module Integration & Registration**:
   - **Entry Points**: Provide standard `Init.py` (headless initialization) and `InitGui.py` (GUI commands, toolbars, and menu registration).
   - **GUI Commands**: Custom tools must extend `Gui.Command` base classes with `GetResources()` (icon, menu text, tooltip) and `Activated()` execution routines.
   - **Addon Manager Support**: Include a standard `package.xml` manifest so the module can be discovered, installed, and updated directly via FreeCAD's Addon Manager (`Std_AddonMgr`).

3. **Units System & Quantity Handling**:
   - Never hardcode raw numeric assumptions for feedrates or dimensions. Use FreeCAD's `FreeCAD.Units` / `FreeCAD.Quantity` system to explicitly handle conversions.
   - Note that internal FreeCAD CAM toolpaths represent feedrates in `mm/s`; the post-processor must convert these to machine units (e.g., `mm/min` or `IPM`) according to the active Job setup.

4. **Scripted Objects & Property Proxies**:
   - For custom parametric features or custom CAM dressups, use the standard `Proxy` object design pattern (`execute(self, obj)` for recomputation and `onChanged(self, obj, prop)` for property updates).

5. **Code Style & Import Conventions**:
   - Follow `PEP8` formatting rules and `PEP257` docstring conventions.
   - Use explicit module-prefixed imports (e.g., `import FreeCAD as App`, `import Path`) rather than wildcard imports (`from Module import *`) to prevent namespace pollution.

---

## OKUMA OSP TECHNICAL REFERENCE & SYNTAX SPECIFICATION

### 1. File Structure & Extensions
- **Main Program File (`.MIN`)**: Primary machining sequence starting with `O` header (e.g., `O1000`) and ending with `M02` or `M30`.
- **Subprogram File (`.SUB`)**: Subroutines called from main or other subprograms, starting with `O` (e.g., `O0100`) and ending with `RTS` (Return from Subroutine).

### 2. Subprogram Calling & Macro Syntax
- **Simple Call (`CALL`)**: `CALL O<name> Q<repeats> <Variable=Expression ...>`
- **Call After Axis Movement (`MODIN` / `MODOUT`)**: Modal subprogram call executed automatically after every positioning move until canceled by `MODOUT`.
- **G-Code User Macros (`G101`–`G120`)**:
  - `G101`–`G110`: Execute `MODIN`-style modal calls.
  - `G111`–`G120`: Execute `CALL`-style simple calls with address arguments (e.g., `G111 X30. Y20.` maps to local variables `PX=30`, `PY=20`).

### 3. User Task Macro Variables & Logic
- **Common Variables (`VC1` – `VC128`)**: Global variables (`VC1`–`VC32` non-volatile).
- **Local Variables (`PA`–`PZ`, `LA`–`LZ`)**: Local subprogram parameters.
- **Branching Statements**: `IF [<expr> <OP> <expr>] N<label>` (Operators: `LT`, `LE`, `EQ`, `NE`, `GE`, `GT`), `GOTO N<label>`.

### 4. Native Area Machining Functions
- **General Format**: `[Mnemonic] Xp_ Yp_ Zp_ I±dx J±dy K_ P_ Q_ R_ D_ F_ FA=_ FB=_`
- **Commands**:
  - `FMILR` / `FMILF`: Face milling roughing (zigzag) / finishing.
  - `PMIL` / `PMILR`: Pocket milling zigzag / spiral pattern.
  - `RMILO` / `RMILI`: Round/rectangular perimeter milling (external / internal).

### 5. Coordinate Calculation Functions (Pattern Functions)
- `BHC Xp Yp Ir Jθ Kn`: Bolt Hole Circle.
- `GRDX` / `GRDY`: Grid array patterns along X or Y.
- `LAA Xp Yp Idist Kcount Jangle`: Line at angle pattern.

---

## POST-PROCESSOR & OPTIMIZATION PIPELINE

1. **Operation Interception & Primitive Mapping**:
   - `Path.Op.Face` → Okuma `FMILR` / `FMILF`.
   - `Path.Op.Pocket_Shape` → Okuma `PMILR` / `PMIL`.
   - `Path.Op.Drilling` & `Path.Op.Array` → `BHC`, `GRDX`, `GRDY`, `LAA` pattern calls combined with `G81`–`G89` cycles.
   - Multi-pass contours → Extract 2D boundary into a `.SUB` file (`RTS`) and iterate depth passes using `MODIN` or `CALL` loops.

2. **Low-Level Character Compression**:
   - Single-digit G/M abbreviation (`G00`→`G0`, `G01`→`G1`, `M03`→`M3`, `T01`→`T1`, `H01`→`H1`).
   - Strip leading zeros (`0.5` → `.5`), trailing zeros (`10.500` → `10.5`), positive signs (`+10` → `10`), and non-essential whitespace/block numbers (`N`).
   - Modal value suppression (omit repeated G-codes, unchanged coordinates `X, Y, Z`, feedrates `F`, spindle speeds `S`).

---

## DELIVERABLES & DIRECTORY LAYOUT

Provide the extension as a clean FreeCAD package directory:

```
OkumaCAM/
├── package.xml                 # Addon Manager metadata
├── Init.py                     # Non-GUI initialization
├── InitGui.py                  # GUI initialization & toolbar/menu setup
├── OkumaOSP_post.py            # FreeCAD CAM post-processor module
├── OkumaOptimizer.py           # Core geometry compression & area machining engine
└── Gui/
    ├── Preferences.py          # PySide Preference page for CAM settings
    └── Resources/              # Icons and UI resources
```
