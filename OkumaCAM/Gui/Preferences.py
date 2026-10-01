"""PySide6 Preferences Page for OkumaCAM Add-On.

Configures OSP controller generation, G111 tool check macro integration,
native area machining, coordinate calculation pattern functions,
subprogram extraction, and low-level code compression.
"""

from __future__ import annotations

import os
from typing import Optional

try:
    import FreeCAD as App
except ImportError:
    App = None

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    # Allow headless fallback for testing or documentation
    QtWidgets = None
    QtCore = None
    QtGui = None


class OkumaCAMPreferencesPage:
    """FreeCAD CAM Preferences Page for Okuma OSP Controls."""

    PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/OkumaCAM"

    def __init__(self, parent: Optional[Any] = None) -> None:
        if QtWidgets is None:
            raise RuntimeError("PySide6 is required to instantiate OkumaCAMPreferencesPage")

        self.form = QtWidgets.QWidget(parent)
        self.form.setWindowTitle("Okuma OSP Settings")
        self._build_ui()
        self.loadSettings()

    def _build_ui(self) -> None:
        """Construct the PySide6 preference layout."""
        main_layout = QtWidgets.QVBoxLayout(self.form)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        # -------------------------------------------------------------
        # Group 1: Machine & Controller Profile
        # -------------------------------------------------------------
        ctrl_group = QtWidgets.QGroupBox("Okuma OSP Controller Configuration", self.form)
        ctrl_layout = QtWidgets.QFormLayout(ctrl_group)
        ctrl_layout.setLabelAlignment(QtCore.Qt.AlignLeft)

        self.combo_controller = QtWidgets.QComboBox(ctrl_group)
        self.combo_controller.addItems(["OSP-P500", "OSP-P300", "OSP-P200", "OSP7000", "OSP5020"])
        ctrl_layout.addRow("Controller Model:", self.combo_controller)

        self.edit_fixture = QtWidgets.QLineEdit("G15 H1", ctrl_group)
        self.edit_fixture.setToolTip("Default work fixture coordinate call (e.g. G15 H1).")
        ctrl_layout.addRow("Default Work Fixture:", self.edit_fixture)

        self.edit_tlo = QtWidgets.QLineEdit("G56", ctrl_group)
        self.edit_tlo.setToolTip("Okuma tool length compensation code (default: G56).")
        ctrl_layout.addRow("Tool Length Offset:", self.edit_tlo)

        main_layout.addWidget(ctrl_group)

        # -------------------------------------------------------------
        # Group 2: Tool Check Routine (G111 / OTCHK in TOOLCHK.LIB)
        # -------------------------------------------------------------
        tc_group = QtWidgets.QGroupBox("Tool Breakage & Pre-Check Routine", self.form)
        tc_layout = QtWidgets.QVBoxLayout(tc_group)

        self.chk_toolcheck = QtWidgets.QCheckBox(
            "Enable G111 Tool Check Macro (OTCHK in TOOLCHK.LIB)", tc_group
        )
        self.chk_toolcheck.setToolTip(
            "Inserts G111 T<tool> following tool changes to invoke the OTCHK macro routine."
        )
        tc_layout.addWidget(self.chk_toolcheck)

        tc_note = QtWidgets.QLabel(
            "<i>Note: On Okuma machines, G111 is reserved for calling the OTCHK subprogram "
            "saved in TOOLCHK.LIB for automated tool verification.</i>",
            tc_group,
        )
        tc_note.setWordWrap(True)
        tc_note.setStyleSheet("color: #64748b; font-size: 11px;")
        tc_layout.addWidget(tc_note)

        main_layout.addWidget(tc_group)

        # -------------------------------------------------------------
        # Group 3: Native OSP Cycles & Pattern Functions
        # -------------------------------------------------------------
        cycle_group = QtWidgets.QGroupBox("Native Area Machining & Pattern Calculation", self.form)
        cycle_layout = QtWidgets.QVBoxLayout(cycle_group)

        self.chk_native_cycles = QtWidgets.QCheckBox(
            "Enable Native Area Machining (FMILR/FMILF, PMIL/PMILR, RMILO/RMILI)", cycle_group
        )
        self.chk_native_cycles.setToolTip(
            "Replaces point-to-point toolpaths with single-block Okuma area cycles when rectangular geometry matches."
        )
        cycle_layout.addWidget(self.chk_native_cycles)

        self.chk_patterns = QtWidgets.QCheckBox(
            "Enable Hole Pattern Functions (BHC, ARC, GRDX, GRDY, LAA)", cycle_group
        )
        self.chk_patterns.setToolTip(
            "Automates bolt hole circles, grids, and line-at-angle arrays combined with canned drilling cycles."
        )
        cycle_layout.addWidget(self.chk_patterns)

        self.chk_m52 = QtWidgets.QCheckBox(
            "Append M52 (Retract to Z Upper Limit on Final Pattern Hole)", cycle_group
        )
        self.chk_m52.setToolTip("Appends M52 to pattern calculation blocks for safe clearance.")
        cycle_layout.addWidget(self.chk_m52)

        main_layout.addWidget(cycle_group)

        # -------------------------------------------------------------
        # Group 4: Subprograms & Arbitrary Volume Clearing
        # -------------------------------------------------------------
        sub_group = QtWidgets.QGroupBox("Subprograms & Volume Clearing", self.form)
        sub_layout = QtWidgets.QVBoxLayout(sub_group)

        self.chk_subprograms = QtWidgets.QCheckBox(
            "Extract Multi-Pass Contours into Auxiliary .SUB Files", sub_group
        )
        self.chk_subprograms.setToolTip(
            "Extracts repeating 2D contour boundaries into a .SUB file (with RTS) called via CALL loops in .MIN."
        )
        sub_layout.addWidget(self.chk_subprograms)

        self.chk_auto_slices = QtWidgets.QCheckBox(
            "Automatic Z-Slice Subprogram Detection for Pockets", sub_group
        )
        self.chk_auto_slices.setToolTip(
            "Detects repeating 2D clearing passes at multiple Z stepdowns and extracts them into parametric subprograms."
        )
        sub_layout.addWidget(self.chk_auto_slices)

        sub_form_layout = QtWidgets.QFormLayout()
        self.combo_draft_mode = QtWidgets.QComboBox(sub_group)
        self.combo_draft_mode.addItems(["G51 Coordinate Scaling", "Tool Radius Offset / PR", "Disabled"])
        sub_form_layout.addRow("Drafted Wall Strategy:", self.combo_draft_mode)

        self.spin_min_slices = QtWidgets.QSpinBox(sub_group)
        self.spin_min_slices.setRange(2, 10)
        self.spin_min_slices.setValue(3)
        sub_form_layout.addRow("Min Slices for Extraction:", self.spin_min_slices)

        self.combo_var_scope = QtWidgets.QComboBox(sub_group)
        self.combo_var_scope.addItems(["Local Variables (LA-LE) - Recommended", "Volatile Common Variables (VC33+)"])
        sub_form_layout.addRow("Variable Register Scope:", self.combo_var_scope)

        sub_layout.addLayout(sub_form_layout)
        main_layout.addWidget(sub_group)


        # -------------------------------------------------------------
        # Group 5: Size Compression & Formatting
        # -------------------------------------------------------------
        opt_group = QtWidgets.QGroupBox("Code Size Optimization & Precision", self.form)
        opt_layout = QtWidgets.QGridLayout(opt_group)

        self.chk_modal = QtWidgets.QCheckBox("Aggressive Modal Suppression (Omit repeated coords)", opt_group)
        opt_layout.addWidget(self.chk_modal, 0, 0, 1, 2)

        self.chk_compress = QtWidgets.QCheckBox("Strip Whitespace & Abbreviate Codes", opt_group)
        opt_layout.addWidget(self.chk_compress, 1, 0, 1, 2)

        opt_layout.addWidget(QtWidgets.QLabel("Coordinate Decimals:"), 2, 0)
        self.spin_precision = QtWidgets.QSpinBox(opt_group)
        self.spin_precision.setRange(1, 6)
        self.spin_precision.setValue(4)
        opt_layout.addWidget(self.spin_precision, 2, 1)

        opt_layout.addWidget(QtWidgets.QLabel("Feedrate Decimals:"), 3, 0)
        self.spin_feed_prec = QtWidgets.QSpinBox(opt_group)
        self.spin_feed_prec.setRange(0, 4)
        self.spin_feed_prec.setValue(1)
        opt_layout.addWidget(self.spin_feed_prec, 3, 1)

        main_layout.addWidget(opt_group)

        # -------------------------------------------------------------
        # Group 6: Electric Spindle Speeder (okuma-electric-speeder-supplement-v2)
        # -------------------------------------------------------------
        speeder_group = QtWidgets.QGroupBox("Electric Spindle Speeder Configuration", self.form)
        speeder_layout = QtWidgets.QVBoxLayout(speeder_group)

        self.chk_speeder = QtWidgets.QCheckBox(
            "Enable Electric Spindle Speeder Mode (Stationary Spindle / M130)", speeder_group
        )
        self.chk_speeder.setToolTip(
            "Bypasses main spindle rotation safety interlock using M130. Main spindle stays at 0 RPM."
        )
        speeder_layout.addWidget(self.chk_speeder)

        spd_form = QtWidgets.QFormLayout()
        self.combo_speeder_scope = QtWidgets.QComboBox(speeder_group)
        self.combo_speeder_scope.addItems(["Finishing Operations Only", "All Operations", "Roughing Operations Only"])
        spd_form.addRow("Speeder Application Scope:", self.combo_speeder_scope)

        self.chk_speeder_dual_m00 = QtWidgets.QCheckBox(
            "Enforce Dual M00 Orientation Checks (Pre-Orientation & Speeder Loading)", speeder_group
        )
        self.chk_speeder_dual_m00.setChecked(True)
        speeder_layout.addWidget(self.chk_speeder_dual_m00)

        self.chk_speeder_verify = QtWidgets.QCheckBox(
            "Verify Zero Main Spindle Movement (Safety Assertion)", speeder_group
        )
        self.chk_speeder_verify.setChecked(True)
        speeder_layout.addWidget(self.chk_speeder_verify)

        self.spin_speeder_retract = QtWidgets.QDoubleSpinBox(speeder_group)
        self.spin_speeder_retract.setRange(10.0, 1000.0)
        self.spin_speeder_retract.setValue(200.0)
        self.spin_speeder_retract.setSuffix(" mm")
        spd_form.addRow("Safe Retract Z for Unloading:", self.spin_speeder_retract)

        speeder_layout.addLayout(spd_form)
        main_layout.addWidget(speeder_group)

        # -------------------------------------------------------------
        # Group 7: Multi-Program Export Configuration
        # -------------------------------------------------------------
        sep_group = QtWidgets.QGroupBox("Multi-Program Rough / Finish Export", self.form)
        sep_layout = QtWidgets.QVBoxLayout(sep_group)

        self.chk_separate_rf = QtWidgets.QCheckBox(
            "Export Roughing and Finishing as Separate G-Code Programs", sep_group
        )
        self.chk_separate_rf.setToolTip(
            "Splits toolpaths into <Job>_ROUGH.MIN and <Job>_FINISH.MIN programs."
        )
        sep_layout.addWidget(self.chk_separate_rf)

        sep_form = QtWidgets.QFormLayout()
        self.edit_rough_suffix = QtWidgets.QLineEdit("_ROUGH", sep_group)
        sep_form.addRow("Roughing Program Suffix:", self.edit_rough_suffix)

        self.edit_finish_suffix = QtWidgets.QLineEdit("_FINISH", sep_group)
        sep_form.addRow("Finishing Program Suffix:", self.edit_finish_suffix)

        sep_layout.addLayout(sep_form)
        main_layout.addWidget(sep_group)

        main_layout.addStretch()

    def get_param_group(self):
        """Retrieve FreeCAD BaseApp parameter group."""
        if App and hasattr(App, "ParamGet"):
            return App.ParamGet(self.PARAM_PATH)
        return None

    def saveSettings(self) -> None:
        """Save settings from UI controls into FreeCAD parameter group."""
        grp = self.get_param_group()
        if not grp:
            return

        grp.SetString("ControllerModel", self.combo_controller.currentText())
        grp.SetString("WorkFixture", self.edit_fixture.text().strip())
        grp.SetString("ToolLengthOffset", self.edit_tlo.text().strip())

        grp.SetBool("EnableToolCheck", self.chk_toolcheck.isChecked())
        grp.SetBool("EnableNativeCycles", self.chk_native_cycles.isChecked())
        grp.SetBool("EnablePatterns", self.chk_patterns.isChecked())
        grp.SetBool("AppendM52", self.chk_m52.isChecked())
        grp.SetBool("EnableSubprograms", self.chk_subprograms.isChecked())
        grp.SetBool("EnableAutoSlices", self.chk_auto_slices.isChecked())
        grp.SetString("DraftMode", self.combo_draft_mode.currentText())
        grp.SetInt("MinSlices", self.spin_min_slices.value())
        grp.SetString("VarScope", self.combo_var_scope.currentText())

        grp.SetBool("EnableModal", self.chk_modal.isChecked())
        grp.SetBool("EnableCompression", self.chk_compress.isChecked())
        grp.SetInt("CoordinatePrecision", self.spin_precision.value())
        grp.SetInt("FeedPrecision", self.spin_feed_prec.value())

        grp.SetBool("EnableSpeeder", self.chk_speeder.isChecked())
        grp.SetString("SpeederScope", self.combo_speeder_scope.currentText())
        grp.SetBool("SpeederDualM00", self.chk_speeder_dual_m00.isChecked())
        grp.SetBool("SpeederVerify", self.chk_speeder_verify.isChecked())
        grp.SetFloat("SpeederRetractZ", self.spin_speeder_retract.value())

        grp.SetBool("SeparateRoughFinish", self.chk_separate_rf.isChecked())
        grp.SetString("RoughSuffix", self.edit_rough_suffix.text().strip())
        grp.SetString("FinishSuffix", self.edit_finish_suffix.text().strip())

    def loadSettings(self) -> None:
        """Load settings from FreeCAD parameter group into UI controls."""
        grp = self.get_param_group()

        # Defaults
        controller = "OSP-P300"
        fixture = "G15 H1"
        tlo = "G56"
        toolcheck = False
        native_cycles = True
        patterns = True
        m52 = True
        subprograms = False
        auto_slices = True
        draft_mode = "G51 Coordinate Scaling"
        min_slices = 3
        var_scope = "Local Variables (LA-LE) - Recommended"
        modal = True
        compress = True
        coord_prec = 4
        feed_prec = 1

        speeder = False
        speeder_scope = "Finishing Operations Only"
        speeder_dual_m00 = True
        speeder_verify = True
        speeder_retract = 200.0

        separate_rf = False
        rough_suffix = "_ROUGH"
        finish_suffix = "_FINISH"

        if grp:
            controller = grp.GetString("ControllerModel", controller)
            fixture = grp.GetString("WorkFixture", fixture)
            tlo = grp.GetString("ToolLengthOffset", tlo)
            toolcheck = grp.GetBool("EnableToolCheck", toolcheck)
            native_cycles = grp.GetBool("EnableNativeCycles", native_cycles)
            patterns = grp.GetBool("EnablePatterns", patterns)
            m52 = grp.GetBool("AppendM52", m52)
            subprograms = grp.GetBool("EnableSubprograms", subprograms)
            auto_slices = grp.GetBool("EnableAutoSlices", auto_slices)
            draft_mode = grp.GetString("DraftMode", draft_mode)
            min_slices = grp.GetInt("MinSlices", min_slices)
            var_scope = grp.GetString("VarScope", var_scope)
            modal = grp.GetBool("EnableModal", modal)
            compress = grp.GetBool("EnableCompression", compress)
            coord_prec = grp.GetInt("CoordinatePrecision", coord_prec)
            feed_prec = grp.GetInt("FeedPrecision", feed_prec)

            speeder = grp.GetBool("EnableSpeeder", speeder)
            speeder_scope = grp.GetString("SpeederScope", speeder_scope)
            speeder_dual_m00 = grp.GetBool("SpeederDualM00", speeder_dual_m00)
            speeder_verify = grp.GetBool("SpeederVerify", speeder_verify)
            speeder_retract = grp.GetFloat("SpeederRetractZ", speeder_retract)

            separate_rf = grp.GetBool("SeparateRoughFinish", separate_rf)
            rough_suffix = grp.GetString("RoughSuffix", rough_suffix)
            finish_suffix = grp.GetString("FinishSuffix", finish_suffix)

        idx = self.combo_controller.findText(controller)
        if idx >= 0:
            self.combo_controller.setCurrentIndex(idx)

        self.edit_fixture.setText(fixture)
        self.edit_tlo.setText(tlo)
        self.chk_toolcheck.setChecked(toolcheck)
        self.chk_native_cycles.setChecked(native_cycles)
        self.chk_patterns.setChecked(patterns)
        self.chk_m52.setChecked(m52)
        self.chk_subprograms.setChecked(subprograms)
        self.chk_auto_slices.setChecked(auto_slices)

        idx_dm = self.combo_draft_mode.findText(draft_mode)
        if idx_dm >= 0:
            self.combo_draft_mode.setCurrentIndex(idx_dm)

        self.spin_min_slices.setValue(min_slices)

        idx_vs = self.combo_var_scope.findText(var_scope)
        if idx_vs >= 0:
            self.combo_var_scope.setCurrentIndex(idx_vs)

        self.chk_modal.setChecked(modal)
        self.chk_compress.setChecked(compress)
        self.spin_precision.setValue(coord_prec)
        self.spin_feed_prec.setValue(feed_prec)

        self.chk_speeder.setChecked(speeder)
        idx_ss = self.combo_speeder_scope.findText(speeder_scope)
        if idx_ss >= 0:
            self.combo_speeder_scope.setCurrentIndex(idx_ss)
        self.chk_speeder_dual_m00.setChecked(speeder_dual_m00)
        self.chk_speeder_verify.setChecked(speeder_verify)
        self.spin_speeder_retract.setValue(speeder_retract)

        self.chk_separate_rf.setChecked(separate_rf)
        self.edit_rough_suffix.setText(rough_suffix)
        self.edit_finish_suffix.setText(finish_suffix)

