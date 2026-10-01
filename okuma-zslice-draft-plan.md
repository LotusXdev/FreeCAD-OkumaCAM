# Implementation Plan: Arbitrary Volume Clearing Z-Slice Subprograms with Drafted Walls

## 1. Executive Summary & Design Alignment
This plan establishes the architecture and implementation for **automatic Z-slice pattern detection, arbitrary pocket/area clearing subprogram extraction, and drafted/tapered wall support** for Okuma OSP controls in FreeCAD 1.1.4 (PySide6).

Based on the interactive design interview, the following technical specifications are locked:
1. **Drafted Wall Execution**: Provide user selection in PySide6 GUI and CLI between:
   - **`G51` Coordinate Scaling**: `G51 Xp Yp P[LD]` around centroid ... `G50`.
   - **Tool Radius Comp / Variable `PR`**: `CALL O... PZ=[LA] PR=2.0 PD=[LD]`.
2. **Extraction Threshold**: Configurable minimum slice count (default: 3 stepdowns) before extracting to `.SUB`; shallow 1-2 pass cuts remain inlined.
3. **Draft Angle Detection**: Hybrid detection: automatically computes geometric contraction/scaling across Z-slices, with explicit override supported via FreeCAD CAM operation properties.
4. **Plunge & Subprogram Boundary**: Parametric subprogram: target depth `PZ` and rapid/plunge clearance `PR` are passed as arguments (`CALL O... PZ=[LA] PR=2.0`), and the subprogram handles the plunge and 2D clearing together.
5. **Variable Allocation**: Local routine variables (`LA`, `LB`, `LC`, `LD`) are preferred in the `.MIN` loop to prevent touching global `VC` registers, with a configurable fallback to volatile common variables (`VC33+`).
6. **Disk Organization**: Combined `.SUB` library: all subprograms for the Job are written to a single `<JobName>.SUB` file alongside `<JobName>.MIN`.

---

## 2. Component Specifications

### 2.1 `OkumaOptimizer.py` (Segmentation, Detection, and Parametric Subprograms)

1. **`ZSlice` Dataclass**:
   - `depth: float`: cutting Z level.
   - `plunge_cmd: Optional[Tuple[str, dict]]`: lead-in/plunge motion.
   - `commands: List[Tuple[str, dict]]`: planar 2D clearing commands.
   - `centroid: Tuple[float, float]`: bounding box center $(X_c, Y_c)$.
   - `bbox: Tuple[float, float, float, float]`: $(X_{min}, X_{max}, Y_{min}, Y_{max})$.
   - `span_x: float`, `span_y: float`.

2. **`ZSliceSegmenter`**:
   - Scans operation `Path.Command` objects.
   - Identifies transitions between plunge, cutting at constant Z, and retract.
   - Segments the toolpath into discrete `ZSlice` structures.

3. **`SliceSimilarityClassifier`**:
   - Analyzes slice sequences ($S_1, S_2, \dots, S_n$):
     - **Vertical (Identical)**: Command structure and coordinates match across slices within tolerance.
     - **Drafted / Tapered**: Slices contract (or expand) by a uniform ratio $s = \frac{\text{dim}_{k+1}}{\text{dim}_k}$ or uniform step-in $\Delta r$ relative to centroid $(X_c, Y_c)$. Computes draft angle $\alpha = \arctan(\frac{\Delta r}{\Delta Z})$.
     - **Unique / Freeform**: Complex 3D variations without geometric symmetry; remains inline.

4. **`SubprogramManager` Updates**:
   - **Parametric Subprogram Emitter**:
     Generates subprogram body:
     ```gcode
     O0200
     ( PARAMETERS: PZ = TARGET DEPTH, PR = PLUNGE CLEARANCE )
     G0 Z[PZ+PR]
     G1 Z[PZ] F...
     ... (2D clearing path) ...
     G0 Z[PZ+PR]
     RTS
     ```
   - **Local Variable Loop Generator (`LA`–`LD`)**:
     Emits clean loop in main `.MIN` program:
     ```gcode
     LA=-2.         (Initial target depth)
     LB=2.          (Stepdown depth)
     LC=-10.        (Final depth)
     (Optional Draft Scaling with G51:)
     LD=1.0         (Initial scale factor)
     LE=0.035       (Scale decrement per pass)
     N100
     G51 X0. Y0. P[LD]
     CALL O0200 PZ=[LA] PR=2.
     G50
     LA=LA-LB
     LD=LD-LE
     IF [LA GE LC] N100
     ```

---

### 2.2 `OkumaOSP_post.py` (Post-Processor Workflow)

1. **Operation Processing Pipeline**:
   - When processing clearing operations (`Pocket_Shape`, `Waterline`, `Pocket`, multi-depth clearing):
   - Check if `ENABLE_SUBPROGRAMS` is active.
   - Run `ZSliceSegmenter`. If `len(slices) >= MIN_SLICES`:
     - Classify similarity (`IDENTICAL` or `DRAFTED`).
     - Emit the parametric `.MIN` loop using local variables (`LA`, `LB`, `LC`, `LD`).
     - Register the 2D clearing routine into `SubprogramManager`.
   - Otherwise, fall back to compressed linear blocks.

2. **CLI Flags**:
   - `--draft-mode=scale` (default: G51 scaling) or `--draft-mode=offset` (cutter comp / PR) or `--draft-mode=none`.
   - `--min-slices=3` (default: 3).
   - `--var-scope=local` (default: LA-LD) or `--var-scope=common` (VC33+).

---

### 2.3 `Gui/Preferences.py` (PySide6 Settings Interface)

Add **"Arbitrary Volume & Pocket Slicing"** group:
- Checkbox: "Automatic Z-Slice Subprogram Detection for Pockets"
- Combo: "Drafted Wall Strategy" (`G51 Coordinate Scaling`, `Tool Radius Offset / PR`, `Disabled`)
- Spinbox: "Minimum Slices for Subprogram Extraction" (1 to 10, default 3)
- Combo: "Variable Register Scope" (`Local Variables (LA-LD) - Recommended`, `Volatile Common Variables (VC33+)`)

---

### 2.4 Test Suite Additions (`tests/test_zslice_subprograms.py`)

1. **`test_segmenter_multislice`**: Verifies slicing of 5-pass toolpath into 5 `ZSlice` objects.
2. **`test_classify_vertical_slices`**: Verifies classification of identical pocket passes.
3. **`test_classify_drafted_slices`**: Verifies detection of tapered cavity with shrinking bounding boxes.
4. **`test_local_var_loop_generation`**: Asserts `LA`, `LB`, `LC`, `IF [LA GE LC] N100` emission without `VC` collisions.
5. **`test_parametric_subprogram_execution`**: Asserts subprogram contains `G0 Z[PZ+PR]`, `G1 Z[PZ]`, and `RTS`.
6. **`test_g51_scaling_draft_loop`**: Asserts `G51 Xp Yp P[LD]` ... `G50` around centroid.
7. **`test_threshold_shallow_pocket`**: Asserts 2-pass pocket remains inline when threshold is 3.

---

## 3. Verification Plan

1. **Automated Unit Tests**:
   Execute via FreeCAD 1.1.4 Python:
   ```powershell
   & "C:\Program Files\FreeCAD 1.1\bin\python.exe" -m unittest discover -t "h:\My Drive\Programming Projects\FreeCad OkumaCAM\OkumaCAM" -s "h:\My Drive\Programming Projects\FreeCad OkumaCAM\OkumaCAM\tests" -v
   ```
2. **FreeCADCmd Test Runner**:
   Execute directly inside headless FreeCAD application console.
