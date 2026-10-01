# Supplemental Specification: Electric Spindle Speeder Integration for Okuma OSP & FreeCAD CAM

## Executive Summary
This document provides an updated technical specification for running an **Electric Spindle Speeder** (high-speed motorized attachment) on Okuma OSP CNC controls (including OSP7000 and OSP-P series) and details how to integrate support for this tool into the **FreeCAD Okuma OSP CAM Post-Processor** (`OkumaOSP_post.py` / `OkumaOptimizer.py`).

Electric spindle speeders feature an independent internal motor and drive mechanism, meaning the main machine spindle remains stationary during cutting operations. Standard CNC safety interlocks block axis cutting feeds when the main spindle is stopped. Bypassing these interlocks requires specific Okuma M-codes, motion modes, dual `M00` unconditional stop checkpoints for operator safety during manual speeder loading, and strict post-processor verification to guarantee zero main spindle movement after loading.

---

## 1. Required Okuma OSP G-Codes & M-Codes

| Code | Description | Functional Role in Speeder Operation |
| :--- | :--- | :--- |
| **`M00`** | Unconditional Stop / Program Stop | Pauses machine execution. Used **before** `M19` orientation to prepare the machine, and **after** `M19` orientation to allow the operator to manually load the electric speeder. |
| **`M130`** | Spindle Rotation Condition for Cutting Feed OFF | Disables the safety interlock that prevents cutting feed (`G01`, `G02`, `G03`) while the main spindle is stopped. Executed after the speeder is loaded. |
| **`M131`** | Spindle Rotation Condition for Cutting Feed ON | Re-enables the default spindle-rotation safety interlock. Must be commanded at program end or speeder section termination. |
| **`M19`** | Spindle Orientation / Position Lock | Indexes and locks the main machine spindle at its oriented angle to align drive keys and accept the speeder's anti-rotation torque arm. |
| **`M05`** | Main Spindle Stop | Ensures the main spindle drive is completely stopped before orientation and interlock bypass. |
| **`G94`** | Feed per Minute Mode | Sets feedrate units to distance per minute (`mm/min` or `IPM`). **Crucial:** In `G95` (Feed per Rev) mode, a stationary main spindle ($0 \text{ RPM}$) yields $0 \text{ mm/min}$ feedrate, freezing axis motion. |

---

## 2. Operational Rules & Safety Workflow

1. **Main Spindle Shutdown (`M05`)**: Execute `M05` to ensure main spindle rotation signals are inactive.
2. **Pre-Orientation Unconditional Stop (`M00`)**: Pause execution prior to orientation so the operator can clear the workspace and prepare for spindle indexing.
3. **Spindle Orientation & Lock (`M19`)**: Execute `M19` to index the spindle to its precise angular position and lock it in place.
4. **Post-Orientation Unconditional Stop & Speeder Loading (`M00`)**: **CRITICAL STEP.** With the main spindle oriented and locked, the machine pauses at `M00`. The operator manually mounts/loads the electric spindle speeder into the spindle taper, ensuring the drive key and anti-rotation torque arm are fully engaged.
5. **Post-Processor Verification (Zero Spindle Movement)**: The code generator/post-processor must strictly verify that NO main spindle rotation commands (`M03`, `M04`), spindle speed assignments (`S`), or automatic tool changes (`M06`) exist anywhere after this second `M00` stop.
6. **Interlock Bypass (`M130`)**: After Cycle Start is pressed following speeder installation, command `M130` to allow axis movement without main spindle rotation.
7. **Feed Mode Selection (`G94`)**: Enforce `G94` (Feed per Minute) mode. Never allow `G95` when operating under `M130`.
8. **Interlock Restoration (`M131`)**: Command `M131` at program completion before returning to standard operation.

---

## 3. FreeCAD Post-Processor Integration Architecture

### A. Configuration & Preference Panel
In `OkumaOSP_post.py` (or the PySide6 preference dialog in FreeCAD 1.1+), include the following toggle settings:
* **`[x] Electric Speeder Mode`**: Master boolean flag enabling speeder logic.
* **`Enforce Dual M00 Orientation Checks`**: Injects `M00` stops before and after `M19`.
* **`Verify Zero Spindle Movement`**: Runs an automated post-generation assertion to ensure no `M03`/`M04`/`S` codes occur after speeder installation.
* **`Speeder Default Feed Mode`**: Enforces `G94` (Feed per Minute).

### B. Header & Cleanup Logic Insertion

#### Program Header Sequence (Dual M00 & Speeder Loading):
```gcode
(--------------------------------------------------)
(FEATURE: ELECTRIC SPINDLE SPEEDER SETUP)
(--------------------------------------------------)
G90 G94          (ABSOLUTE POSITIONING & FEED PER MINUTE)
M05              (ENSURE MAIN SPINDLE STOPPED)
(MSG, READY FOR SPINDLE ORIENTATION - PRESS CYCLE START)
M00              (1ST UNCONDITIONAL STOP: PRE-ORIENTATION CHECK)
M19              (INDEX AND LOCK MAIN SPINDLE ORIENTATION)
(MSG, LOAD SPEEDER NOW & ENGAGE TORQUE ARM - PRESS CYCLE START)
M00              (2ND UNCONDITIONAL STOP: OPERATOR LOADS SPEEDER)
M130             (DISABLE SPINDLE ROTATION INTERLOCK FOR CUTTING FEED)
(--------------------------------------------------)
```

#### Program Cleanup & Exit:
```gcode
(--------------------------------------------------)
(RESTORE MACHINE INTERLOCKS & REMOVE SPEEDER)
(--------------------------------------------------)
G00 Z200.        (RETRACT TO SAFE Z LEVEL)
M131             (RE-ENABLE SPINDLE ROTATION SAFETY INTERLOCK)
(MSG, REMOVE ELECTRIC SPEEDER FROM SPINDLE)
M00              (UNCONDITIONAL STOP FOR SPEEDER UNLOADING)
M02              (PROGRAM END)
```

---

## 4. Post-Processor Python Logic & Code Verification

The following Python code demonstrates the post-processing and verification routines in `OkumaOSP_post.py`:

```python
# OkumaOSP_post.py - Electric Speeder Handler & Verification Module

class SpeederPostError(Exception):
    """Raised when unsafe spindle movement is detected after speeder loading."""
    pass


def process_speeder_header():
    """Generates the dual-M00 orientation and speeder loading header."""
    return [
        "G90 G94",
        "M05",
        "(MSG, READY FOR SPINDLE ORIENTATION - PRESS CYCLE START)",
        "M00",
        "M19",
        "(MSG, LOAD SPEEDER NOW & ENGAGE TORQUE ARM - PRESS CYCLE START)",
        "M00",
        "M130"
    ]


def verify_no_spindle_movement_after_speeder_load(gcode_blocks):
    """
    Verifies that no main spindle movement (M03, M04, S-codes, M06)
    occurs after the second M00 unconditional stop (speeder load point).
    """
    speeder_loaded = False
    m00_count = 0
    
    for line_num, block in enumerate(gcode_blocks, start=1):
        clean_block = block.split('(')[0].strip().upper()  # Ignore comments
        tokens = clean_block.split()
        
        # Track M00 occurrences in setup header
        if "M00" in tokens or "M0" in tokens:
            m00_count += 1
            if m00_count == 2:
                speeder_loaded = True
                continue
                
        if speeder_loaded:
            # Check for M03 / M04
            if any(m in tokens for m in ["M03", "M3", "M04", "M4"]):
                raise SpeederPostError(
                    f"CRITICAL SAFETY ERROR Line {line_num}: "
                    f"Spindle start command detected after speeder load! Block: '{block}'"
                )
            # Check for S-codes (spindle RPM)
            for token in tokens:
                if token.startswith('S') and len(token) > 1 and token[1:].isdigit():
                    if int(token[1:]) > 0:
                        raise SpeederPostError(
                            f"CRITICAL SAFETY ERROR Line {line_num}: "
                            f"Spindle speed S > 0 detected after speeder load! Block: '{block}'"
                        )
            # Check for Tool Change M06
            if any(m in tokens for m in ["M06", "M6"]):
                raise SpeederPostError(
                    f"CRITICAL SAFETY ERROR Line {line_num}: "
                    f"Automatic tool change M06 detected during speeder operation! Block: '{block}'"
                )

    print("SUCCESS: Verified zero main spindle movement after speeder installation.")
    return True
```

---

## 5. Sample Verified G-Code Output

Below is an example of a verified Okuma OSP program for an electric spindle speeder:

```gcode
O2001
(ELECTRIC SPEEDER - HIGH SPEED ENGRAVING)
G90G94
M05
(MSG, READY FOR SPINDLE ORIENTATION - PRESS CYCLE START)
M00
M19
(MSG, LOAD SPEEDER NOW & ENGAGE TORQUE ARM - PRESS CYCLE START)
M00
M130
G0X0.Y0.Z50.
Z2.
G1Z-.1F100.
X10.
Y10.
X0.
Y0.
G0Z50.
M131
(MSG, REMOVE ELECTRIC SPEEDER FROM SPINDLE)
M00
M02
```

---

## Summary Checklist for Machine Operators
1. Press Cycle Start at the **1st `M00`** stop to allow the machine to orient and lock the main spindle (`M19`).
2. At the **2nd `M00`** stop, manually load the electric spindle speeder into the spindle taper and verify that the anti-rotation torque arm is properly seated in the drive key block.
3. Confirm that `G94` feed per minute is active before resuming execution.
4. Press Cycle Start to execute `M130` and initiate machining moves.
5. At program completion, verify `M131` re-enables interlocks before removing the speeder at the final `M00` stop.
