# Okuma OSP Native Area Machining Functions & User Task Macro Logic

This guide provides a comprehensive technical reference for **Okuma OSP (OSP7000, OSP5020, OSP-P series)** native area machining functions, coordinate pattern calculation functions, subprogram call mechanisms, and User Task macro variables and control logic.

---

## 1. Native Area Machining Functions (Optional OSP Feature)

Okuma OSP controls feature built-in Area Machining functions that allow high-level rectangular surface, pocket, and perimeter milling operations to be commanded in a single line of G-code. This bypasses point-to-point CAM toolpath generation and significantly reduces program file size.

### General Command Format

```gcode
[(Mnemonic)] Xp_ Yp_ Zp_ I±dx J±dy K_ P_ Q_ R_ D_ F_ FA=_ FB=_
```

### Parameter Definitions

| Parameter | Function | Description & Behavior |
| :--- | :--- | :--- |
| **Mnemonic** | Function Code | Defines the specific area milling strategy (`FMILR`, `FMILF`, `PMIL`, `PMILR`, `RMILO`, `RMILI`). |
| **`Xp`, `Yp`** | Reference Point | Reference point coordinates on the selected plane (X/Y or U/V). Defaults to current position if omitted. |
| **`Zp`** | Finish Level | Target Z-level of the finished bottom surface. Absolute height in `G90`; incremental depth in `G91`. |
| **`I`** | X-Length (`±dx`) | Length of machining area along the X-axis from the reference point. Sign determines direction. |
| **`J`** | Y-Length (`±dy`) | Length of machining area along the Y-axis from the reference point. Sign determines direction. |
| **`K`** | Finish Allowance | Stock allowance left for the finish pass on walls/bottom. Default is `0`. |
| **`P`** | Stepover Ratio | Cutting width stepover expressed as a percentage of cutter diameter (e.g., `P70` = 70%). Default is `70`. |
| **`Q`** | Depth per Pass | Axial depth of cut per cycle (Z stepdown). If omitted, a single cut reaches the finish level. |
| **`R`** | Rapid Return Level | Z-axis clearance/return level for rapid traverse moves. |
| **`D`** | Tool Offset No. | Cutter radius compensation register number (`D01`–`D99`). |
| **`F`** | Cutting Feedrate | Primary cutting feedrate. Saved modally for subsequent blocks. |
| **`FA=`** | Transition Feedrate | Feedrate used after retracting to point R level and transitioning. Default is `4 * F`. |
| **`FB=`** | Z Infeed Feedrate | Feedrate used during Z-axis plunge/infeed into material. Default is `F / 4`. |

---

### Area Machining Mnemonics & Tool Movement

#### 1. Face Milling Functions (`FMILR`, `FMILF`)
- **`FMILR` (Roughing / On-Workpiece)**: Cyclically machines a rectangular surface in a zigzag pattern. The tool remains engaged with the workpiece during direction turns at the ends of strokes.
- **`FMILF` (Finishing / Off-Workpiece)**: Cyclically machines a rectangular surface in parallel strokes, feeding the tool completely off the workpiece edge before repositioning for the next pass.

#### 2. Pocket Milling Functions (`PMIL`, `PMILR`)
- **`PMIL` (Zigzag Pocketing)**: Clears an internal rectangular cavity using a parallel zigzag pattern, followed by a peripheral clean-up pass along the pocket walls.
- **`PMILR` (Spiral Pocketing)**: Clears an internal rectangular cavity using a continuous spiral toolpath expanding outward from the center (or inward), maintaining uniform chip load.

#### 3. Round / Perimeter Milling Functions (`RMILO`, `RMILI`)
- **`RMILO` (External Perimeter Milling)**: Cycles around the outer perimeter of a rectangular boss or block to machine external side walls over stock allowance `Q`.
- **`RMILI` (Internal Perimeter Milling)**: Cycles around the inner perimeter of a rectangular cavity wall over stock allowance `Q`.

---

## 2. Coordinate Calculation Pattern Functions

Coordinate Calculation functions automate repetitive hole positioning patterns (bolt hole circles, grids, lines) when combined with canned drilling/boring cycles (`G81`–`G89`).

### 1. Bolt Hole Circle (`BHC`)
Calculates hole coordinates evenly spaced on a circular arc or full circle.
```gcode
BHC Xp_ Yp_ I_ J_ K_
```
- **`Xp`, `Yp`**: Center coordinates of the circle.
- **`I`**: Radius of the bolt circle (`r > 0`).
- **`J`**: Starting angle ($\theta$) relative to the positive horizontal axis (CCW positive).
- **`K`**: Number of holes ($n$). Positive for CCW stepping; negative for CW stepping.

### 2. Arc Pattern (`ARC`)
Calculates hole coordinates at irregular or regular angular increments on an arc.
```gcode
ARC Xp_ Yp_ I_ Q±Δθ1 K1_ Q±Δθ2 K2_ ... J±θ
```
- **`I`**: Radius of the arc.
- **`Q`**: Angular increment ($\Delta\theta$) for subsequent holes.
- **`K`**: Number of holes at interval `Q` (default `1`).
- **`J`**: Starting angle relative to horizontal axis.

### 3. Grid Patterns (`GRDX`, `GRDY`)
Calculates a rectangular matrix array of holes along horizontal (`GRDX`) or vertical (`GRDY`) primary scan axes.
```gcode
GRDX Xp_ Yp_ I±dx J±dy Knx Pny
```
- **`I`**: Pitch along the X-axis (`dx`).
- **`J`**: Pitch along the Y-axis (`dy`).
- **`K`**: Number of holes along the X-axis (`nx`).
- **`P`**: Number of holes along the Y-axis (`ny`).

### 4. Line at Angle (`LAA`)
Calculates hole coordinates along a straight line angled relative to the horizontal axis.
```gcode
LAA Xp_ Yp_ I±d1 Kn1 I±d2 Kn2 ... J±θ
```
- **`I`**: Pitch distance (`d`) along the line.
- **`K`**: Number of points at distance `I`.
- **`J`**: Angle ($\theta$) of the line relative to the horizontal axis.

### 5. Auxiliary Pattern Modifiers
- **`OMIT R_ R_`**: Omits specific hole sequence numbers from execution (e.g., `OMIT R3 R7` skips the 3rd and 7th holes).
- **`RSTRT R_`**: Restarts pattern drilling execution starting from hole index `R` (useful after tool breakages).
- **`M52`**: Retracts the Z-axis to the upper machine limit after completing the final hole in the pattern.

---

## 3. Subprogram Structure & Macro Calls

Okuma OSP supports modular programming using subprograms (`.SUB` files) and macro routines.

### File Extensions & Program Headers
- **Main Program (`.MIN`)**: Primary program structure starting with an `O` header (e.g., `O1000`) and ending with `M02` or `M30`.
- **Subprogram (`.SUB`)**: Subroutines stored separately or appended, starting with an `O` header (e.g., `O0100`) and ending with **`RTS`** (Return from Subroutine).

---

### Subprogram Call Mechanisms

#### 1. Simple Subprogram Call (`CALL`)
Executes a target subprogram immediately.
```gcode
CALL O0100 Q1 PA=10.0 PB=25.5
```
- **`O`**: Subprogram name.
- **`Q`**: Number of repetitions (default `1`).
- **`PA=`, `PB=`**: Local variable parameter assignments passed into the subprogram.

#### 2. Modal Call After Axis Movement (`MODIN` / `MODOUT`)
Establishes a modal subprogram call mode where the target subprogram executes automatically after every subsequent axis positioning move.
```gcode
MODIN O0100 PA=5.0
X10. Y20.    (Subprogram O0100 executes after this move)
X30. Y40.    (Subprogram O0100 executes again after this move)
MODOUT       (Cancels active MODIN mode)
```
*Note: OSP supports up to 8 levels of nested `MODIN` calls.*

#### 3. G-Code User Macros (`G101`–`G120`)
Maps standard G-codes directly to custom subprograms:
- **`G101`–`G110`**: Triggers `MODIN`-style modal subprogram calls.
- **`G111`–`G120`**: Triggers `CALL`-style single subprogram calls.
- **Parameter Passing**: Address letters passed on the G-code line automatically populate corresponding local variables prefixed with `P` inside the macro routine:
  ```gcode
  G111 X30. Y20. I10. J5.  -> Passes PX=30.0, PY=20.0, PI=10.0, PJ=5.0
  ```

---

## 4. User Task Macro Variables & Control Logic

Okuma User Task provides variable storage, mathematical expression evaluation, conditional branching, and I/O signal manipulation.

### Variable Types & Scope

| Variable Type | Syntax | Scope & Characteristics |
| :--- | :--- | :--- |
| **Common Variables** | `VC1` – `VC128` | **Global**. Shared across main programs, subprograms, and schedule programs.<br>• `VC1`–`VC32`: Non-volatile (retained across power cycles).<br>• `VC33`–`VC128`: Volatile (cleared to `EMPTY` upon power-on).<br>• Array format supported: `VC[1]`, `VC[VC1 + 1]`. |
| **Local Variables** | `PA`–`PZ`, `LA`–`LZ` | **Routine-Scoped**. Local to the active program or subprogram.<br>• Up to 255 local variables per subroutine.<br>• Erased upon subprogram completion (`RTS`) or NC reset.<br>• Parameter arguments in `G111` calls map to `PX`, `PY`, `PZ`, etc. |
| **System Variables** | `V...` | **System State**. Provides read/write access to NC status, tool data, work offsets, and operating parameters.<br>• `VZOFX[1]`: X-axis work offset value.<br>• `VTLCN`: Active tool number.<br>• `VTLNN`: Next tool number staged in magazine.<br>• `VGCOD[group]`: Active G-code in specified modal group.<br>• `VMCOD[group]`: Active M-code in specified modal group. |
| **I/O Variables** | `VDIN[n]`, `VDOUT[n]` | **Hardware Interface**. Reads external hardware input signals (`VDIN`) or sets output signals (`VDOUT`) on the machine PLC/EC interface. |

---

### Program Branching & Control Flow

#### 1. Unconditional Branch (`GOTO`)
Jumps directly to a sequence number or alphanumeric sequence label:
```gcode
GOTO N100
GOTO NA01    (Jump to sequence label NA01)
```

#### 2. Conditional Branch (`IF`)
Evaluates a logical expression and jumps to a target sequence block if true:
```gcode
IF [Expression OPERATOR Expression] Nlabel
IF [Expression OPERATOR Expression] GOTO Nlabel
```

#### Relational Operators
*Note: Spaces are required on both sides of relational operators inside brackets.*

| Operator | Meaning | Example | Behavior |
| :---: | :--- | :--- | :--- |
| **`LT`** | Less Than ($<$) | `IF [VC1 LT 5] N100` | Jumps to `N100` if `VC1` $< 5$. |
| **`LE`** | Less Than or Equal ($\le$) | `IF [VC1 LE 5] N100` | Jumps to `N100` if `VC1` $\le 5$. |
| **`EQ`** | Equal To ($=$) | `IF [VC1 EQ 5] N100` | Jumps to `N100` if `VC1` $= 5$. |
| **`NE`** | Not Equal To ($\ne$) | `IF [VC1 NE 5] N100` | Jumps to `N100` if `VC1` $\ne 5$. |
| **`GT`** | Greater Than ($>$) | `IF [VC1 GT 5] N100` | Jumps to `N100` if `VC1` $> 5$. |
| **`GE`** | Greater Than or Equal ($\ge$) | `IF [VC1 GE 5] N100` | Jumps to `N100` if `VC1` $\ge 5$. |

#### Checking Omitted / Unset Arguments
When writing macro subprograms, omitted address arguments evaluate to `EMPTY`:
```gcode
N1 IF [PI NE EMPTY] N2    (Process X/I parameter if specified)
   ... (Fallback logic if I parameter was omitted)
N2 IF [PJ NE EMPTY] N3    (Process Y/J parameter if specified)
```

---

### Mathematical & Trigonometric Functions

User Task expressions support standard arithmetic operations (`+`, `-`, `*`, `/`) and built-in functions:

```gcode
VC1 = SIN[30]           ; Sine (Result: 0.5)
VC1 = COS[VC2]          ; Cosine
VC1 = TAN[45]           ; Tangent (Result: 1.0)
VC1 = ATAN[1]           ; Arctangent 1 (-90° to +90°, Result: 45.0)
VC2 = ATAN2[Y, X]       ; Arctangent 2 (-180° to +180°)
VC1 = SQRT[VC2 + 4]     ; Square Root
VC1 = ABS[20 - VC2]     ; Absolute Value
VC1 = MOD[VC2, 7]       ; Modulo / Remainder (e.g. MOD[60, 7] = 4)
```

#### Integer Conversion Functions
*Note: In metric mode, integer conversion calculations operate in micron ($0.001\text{ mm}$) units.*

- **`ROUND[...]`**: Rounds off an expression to the nearest integer.
- **`FIX[...]`**: Truncates decimal values down to an integer.
- **`FUP[...]`**: Raises decimal values up to the next higher integer.
