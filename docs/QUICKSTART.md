# OkumaCAM Quick Start Tutorial

This guide walks you through setting up and running a complete machining workflow with **OkumaCAM** in FreeCAD:
1. Setting up tools for roughing and finishing.
2. Adding an **Okuma Contour Pocket** operation with automatic **Inscribed Volume Detection**.
3. Configuring the **Electric Spindle Speeder** for high-speed finishing.
4. Exporting separate roughing and finishing G-code programs.
5. Transferring and running the programs on an Okuma OSP control.

---

## Prerequisites

1. **FreeCAD 1.0 or 1.1** installed.
2. **OkumaCAM** installed in your FreeCAD `Mod` directory (see [README.md](../README.md#installation)).
3. Okuma CNC Machining Center with OSP7000, OSP-E100, OSP-P200, OSP-P300, or OSP-P500 control.
4. (Optional) Okuma [`TOOLCHK.LIB`](../TOOLCHK.LIB) registered on your CNC control for `G111` automatic tool pre-staging.

---

## Step 1: Create a CAM Job and Add Tools

1. Open your 3D CAD model in FreeCAD.
2. Switch to the **CAM** workbench.
3. Click **Create Job** (`Path_Job`). Select your solid model as the base object.
4. In the Job setup:
   - Add **Tool 1**: e.g., `1/2" (12.7mm) Flat Endmill` (Roughing Tool). Set spindle speed to `2500 RPM`, horizontal feed to `1000 mm/min`.
   - Add **Tool 2**: e.g., `1/4" (6.35mm) Flat/Ball Endmill` (Finishing Tool). Set horizontal feed to `1500 mm/min`.
5. Click **OK** to create the Job.

---

## Step 2: Create an Okuma Contour Pocket Operation

1. In the 3D view, select the bottom face or perimeter boundary of the pocket cavity you want to machine.
2. In the toolbar, click the **Contour Pocket (Okuma)...** icon:
   ![Okuma Pocket Icon](../OkumaCAM/Gui/Resources/okuma_pocket.svg)
3. The **Okuma Contour Pocket** TaskPanel opens with live geometry diagnostics:
   - **Inscribed Core Detection**: OkumaCAM immediately analyzes the polygon boundary using the Maximum Inscribed Rectangle (MIR) and Largest Inscribed Circle (LIC) algorithms.
   - You will see the detected core type (e.g. `RECTANGLE` or `CIRCLE`) and the coverage ratio (e.g. `Coverage: 68.4%`).
4. In the TaskPanel:
   - **Roughing Tool**: Select `T1`.
   - **Finishing Tool**: Select `T2`.
   - **Enable Finishing**: Checked.
   - **Rough StepDown**: e.g. `2.5 mm`.
   - **Finish StepDown**: e.g. `1.0 mm`.
   - **Finish Allowance**: e.g. `0.5 mm` (material left for the finishing pass).
   - **Pocket Strategy**: Leave on `Auto` (automatically picks hybrid canned cycle clearing when coverage $\ge 50\%$).
   - **Rough Cycle**: `Helical / Spiral (PMILR)`.
   - **Finish Cycle**: `Perimeter Only (RMILI)`.
5. Click **OK**. FreeCAD computes the toolpaths and displays the toolpath wireframes in the 3D view.

---

## Step 3: Configure the Electric Spindle Speeder (Optional)

If you are using an electric motorized spindle speeder attachment (e.g. 24,000 to 60,000 RPM motorized unit) for the finishing pass:

1. Double-click the **OkumaContourPocket** operation in the tree view to open its TaskPanel.
2. Check the box: **Use Electric Spindle Speeder for Finishing**.
3. Click **OK**.
4. Open **Edit -> Preferences -> OkumaCAM**:
   - Under **Electric Spindle Speeder Configuration**:
     - Check **Enable Electric Spindle Speeder Mode**.
     - Set **Speeder Application Scope** to `Finishing Operations Only`.
     - Ensure **Enforce Dual M00 Orientation Checks** is checked.
     - Ensure **Verify Zero Main Spindle Movement** is checked.
     - Set **Safe Retract Z for Unloading** (default: `200.0 mm`).
5. Click **Apply** and **OK**.

---

## Step 4: Configure Multi-Program Rough / Finish Export

To separate roughing and finishing passes into two clean G-code files:

1. Open **Edit -> Preferences -> OkumaCAM**.
2. Under **Multi-Program Rough / Finish Export**:
   - Check **Export Roughing and Finishing as Separate G-Code Programs**.
   - Set **Roughing Program Suffix** to `_ROUGH` (default).
   - Set **Finishing Program Suffix** to `_FINISH` (default).
3. Click **OK**.

---

## Step 5: Export Okuma OSP G-Code

1. In the tree view, select your CAM **Job**.
2. Press `Ctrl+Shift+O` (or click **CAM -> Export Okuma OSP G-Code...**).
3. In the file save dialog, select your target file path (e.g. `CavityPart.MIN`).
4. Click **Save**.
5. OkumaCAM automatically generates two separate programs in the destination folder:
   - `CavityPart_ROUGH.MIN`: Roughing program for the standard machine spindle.
   - `CavityPart_FINISH.MIN`: Finishing program with speeder safety headers and cleanup.
   - (Plus `CavityPart_ROUGH.SUB` and `CavityPart_FINISH.SUB` if subprograms are enabled).

A dialog notification confirms the generated files.

---

## Step 6: Inspecting the Generated G-Code

### Roughing Program (`CavityPart_ROUGH.MIN`)
```gcode
O1000
(==================================================)
( OKUMA OSP CAM POST-PROCESSOR )
( PROGRAM STAGE: ROUGH )
( TOOLCHECK (OTCHK): ENABLED (G111) )
(==================================================)
G21 G17 G90 G80 G40
G15 H1
(ContourPocketOp)
NAT01
T1 M6
G15 H1
G56 H1
G111 T1 Q2
S2500 M3
M8
( INSCRIBED CORE: RECTANGLE PMILR )
PMILR X15. Y15. Z-12. I70. J50. K.5 Q2.5 R2. P75. D1 F1000.
( RESIDUAL MARGIN ROUGHING )
LA=-2.5
N100 CALL O0100 PZ=[LA] PR=2.
LA=[LA-2.5]
IF [LA GE -12.] N100
G80
M9
M5
G0 Z50.
M02
```

### Finishing Program (`CavityPart_FINISH.MIN`)
```gcode
O1001
(==================================================)
( OKUMA OSP CAM POST-PROCESSOR )
( PROGRAM STAGE: FINISH )
( ELECTRIC SPINDLE SPEEDER: ACTIVE (STATIONARY SPINDLE) )
( TOOLCHECK (OTCHK): ENABLED (G111) )
(==================================================)
(--------------------------------------------------)
(FEATURE: ELECTRIC SPINDLE SPEEDER SETUP)
(--------------------------------------------------)
G90 G94
M05
(MSG, READY FOR SPINDLE ORIENTATION - CLEAR SPINDLE & PRESS CYCLE START)
M00
M19
(MSG, LOAD SPEEDER NOW & ENGAGE TORQUE ARM - PRESS CYCLE START)
M00
M130
(--------------------------------------------------)
G21 G17 G90 G80 G40
G15 H1
(ContourPocketOp)
G15 H1
G56 H2
( FINISHING PASS: RMILI PERIMETER )
RMILI X15. Y15. Z-12. I70. J50. K0. Q1. R2. D2 F1500.
G80
M9
(--------------------------------------------------)
(RESTORE MACHINE INTERLOCKS & REMOVE SPEEDER)
(--------------------------------------------------)
G00 Z200.
M131
(MSG, REMOVE ELECTRIC SPEEDER FROM SPINDLE)
M00
M02
```

---

## Step 7: Running on the Okuma Machine

1. **Load `CavityPart_ROUGH.MIN`** into your Okuma OSP control memory (via USB or network DNC).
2. Verify Tool 1 is loaded in the spindle.
3. Run `CavityPart_ROUGH.MIN` in Auto mode. The machine will rough out the core using `PMILR` and clear remaining corners with the subprogram loop.
4. When roughing completes, the machine parks safely at `Z50.` with `M02`.
5. **Load `CavityPart_FINISH.MIN`** into the control.
6. Press **Cycle Start**:
   - The machine stops at the first `M00` with the prompt: `READY FOR SPINDLE ORIENTATION`. Ensure the spindle nose is clear and press Cycle Start.
   - The control locks the main spindle at 0 RPM using `M19` and stops at the second `M00`: `LOAD SPEEDER NOW & ENGAGE TORQUE ARM`.
   - Mount your electric speeder into the spindle nose and secure the torque arm. Connect the power umbilical and turn on the speeder controller.
   - Press **Cycle Start**: The control commands `M130` and executes high-speed perimeter finishing with `RMILI`.
   - When cutting finishes, the machine retracts to safe Z (`G00 Z200.`), commands `M131` to restore interlocks, and stops at `M00`: `REMOVE ELECTRIC SPEEDER FROM SPINDLE`.
   - Turn off the speeder, disconnect the umbilical, remove the speeder, and press Cycle Start to finish (`M02`).
