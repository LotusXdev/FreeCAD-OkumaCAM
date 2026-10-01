"""OkumaCAM TaskPanel for Contour Pocket Operation."""

from __future__ import annotations

from typing import Any, Optional

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    QtWidgets = None
    QtCore = None
    QtGui = None

try:
    import FreeCAD as App
    import FreeCADGui as Gui
except ImportError:
    App = None
    Gui = None


class TaskPanelContourPocket:
    """TaskPanel dialog for configuring OkumaContourPocket operations."""

    def __init__(self, obj: Any) -> None:
        self.obj = obj
        has_app = QtWidgets is not None and QtWidgets.QApplication.instance() is not None
        self.form = QtWidgets.QWidget() if has_app else None
        if self.form:
            self._setup_ui()
            self._load_from_obj()

    def _setup_ui(self) -> None:
        self.form.setWindowTitle("Okuma Contour Pocket Settings")
        layout = QtWidgets.QVBoxLayout(self.form)

        # 1. Tool Selection Group
        tool_grp = QtWidgets.QGroupBox("Dual-Tool Selection")
        tool_layout = QtWidgets.QFormLayout(tool_grp)

        self.combo_rough_tool = QtWidgets.QComboBox()
        self.combo_finish_tool = QtWidgets.QComboBox()
        self.chk_enable_finish = QtWidgets.QCheckBox("Enable Dedicated Finishing Pass")
        self.chk_enable_finish.setChecked(True)
        self.chk_use_speeder = QtWidgets.QCheckBox("Use Electric Spindle Speeder for Finishing")
        self.chk_use_speeder.setChecked(False)

        tool_layout.addRow("Roughing Tool:", self.combo_rough_tool)
        tool_layout.addRow("Finishing Tool:", self.combo_finish_tool)
        tool_layout.addRow("", self.chk_enable_finish)
        tool_layout.addRow("", self.chk_use_speeder)
        layout.addWidget(tool_grp)

        # 2. Depths Group
        depth_grp = QtWidgets.QGroupBox("Depths & Stepdown")
        depth_layout = QtWidgets.QFormLayout(depth_grp)

        self.spin_start_z = QtWidgets.QDoubleSpinBox()
        self.spin_start_z.setRange(-1000.0, 1000.0)
        self.spin_start_z.setSuffix(" mm")

        self.spin_final_z = QtWidgets.QDoubleSpinBox()
        self.spin_final_z.setRange(-1000.0, 1000.0)
        self.spin_final_z.setSuffix(" mm")

        self.spin_rough_stepdown = QtWidgets.QDoubleSpinBox()
        self.spin_rough_stepdown.setRange(0.01, 100.0)
        self.spin_rough_stepdown.setValue(2.0)
        self.spin_rough_stepdown.setSuffix(" mm")

        self.spin_finish_stepdown = QtWidgets.QDoubleSpinBox()
        self.spin_finish_stepdown.setRange(0.01, 100.0)
        self.spin_finish_stepdown.setValue(1.0)
        self.spin_finish_stepdown.setSuffix(" mm")

        depth_layout.addRow("Start Depth:", self.spin_start_z)
        depth_layout.addRow("Final Depth:", self.spin_final_z)
        depth_layout.addRow("Rough Stepdown (Q):", self.spin_rough_stepdown)
        depth_layout.addRow("Finish Stepdown:", self.spin_finish_stepdown)
        layout.addWidget(depth_grp)

        # 3. Inscribed Volume & Strategy Group
        strat_grp = QtWidgets.QGroupBox("Inscribed Volume & Strategy")
        strat_layout = QtWidgets.QFormLayout(strat_grp)

        self.combo_strategy = QtWidgets.QComboBox()
        self.combo_strategy.addItems(["Auto", "Force Canned Cycle", "Force Subprogram", "Standard"])

        self.spin_coverage_threshold = QtWidgets.QDoubleSpinBox()
        self.spin_coverage_threshold.setRange(0.05, 0.95)
        self.spin_coverage_threshold.setSingleStep(0.05)
        self.spin_coverage_threshold.setValue(0.40)

        self.combo_rough_cycle = QtWidgets.QComboBox()
        self.combo_rough_cycle.addItems(["PMILR (Spiral)", "PMIL (Zigzag)"])

        self.combo_finish_cycle = QtWidgets.QComboBox()
        self.combo_finish_cycle.addItems(["RMILI (Perimeter)", "Contour Sweep"])

        self.spin_finish_allowance = QtWidgets.QDoubleSpinBox()
        self.spin_finish_allowance.setRange(0.0, 50.0)
        self.spin_finish_allowance.setValue(0.5)
        self.spin_finish_allowance.setSuffix(" mm")

        strat_layout.addRow("Machining Strategy:", self.combo_strategy)
        strat_layout.addRow("Min Inscribed Coverage:", self.spin_coverage_threshold)
        strat_layout.addRow("Rough Canned Cycle:", self.combo_rough_cycle)
        strat_layout.addRow("Finish Canned Cycle:", self.combo_finish_cycle)
        strat_layout.addRow("Finish Stock (K):", self.spin_finish_allowance)
        layout.addWidget(strat_grp)

        # 4. Status Group
        status_grp = QtWidgets.QGroupBox("Inscribed Volume Diagnostics")
        status_layout = QtWidgets.QVBoxLayout(status_grp)
        self.lbl_status = QtWidgets.QLabel("Detected Core: Evaluating...")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #0284c7;")
        status_layout.addWidget(self.lbl_status)
        layout.addWidget(status_grp)

        layout.addStretch()

    def _populate_tools(self) -> None:
        """Populate tool combo boxes from active CAM Job."""
        self.combo_rough_tool.clear()
        self.combo_finish_tool.clear()
        self.combo_rough_tool.addItem("None", None)
        self.combo_finish_tool.addItem("None", None)

        if not App or not App.ActiveDocument:
            return

        doc = App.ActiveDocument
        for o in doc.Objects:
            if hasattr(o, "Proxy") and getattr(o.Proxy, "Type", "") == "ToolController":
                lbl = getattr(o, "Label", o.Name)
                t_num = getattr(o, "ToolNumber", 1)
                self.combo_rough_tool.addItem(f"T{t_num}: {lbl}", o)
                self.combo_finish_tool.addItem(f"T{t_num}: {lbl}", o)

    def _load_from_obj(self) -> None:
        if not self.obj:
            return
        self._populate_tools()

        def _val(attr: str, default: float) -> float:
            v = getattr(self.obj, attr, default)
            return float(getattr(v, "Value", v))

        self.spin_start_z.setValue(_val("StartDepth", 0.0))
        self.spin_final_z.setValue(_val("FinalDepth", -10.0))
        self.spin_rough_stepdown.setValue(_val("RoughStepDown", 2.0))
        self.spin_finish_stepdown.setValue(_val("FinishStepDown", 1.0))
        self.spin_finish_allowance.setValue(_val("FinishAllowance", 0.5))

        cov = getattr(self.obj, "InscribedMinCoverage", 0.40)
        self.spin_coverage_threshold.setValue(float(cov))

        strat = getattr(self.obj, "PocketStrategy", "Auto")
        idx = self.combo_strategy.findText(str(strat))
        if idx >= 0:
            self.combo_strategy.setCurrentIndex(idx)

        en_fin = getattr(self.obj, "EnableFinishing", True)
        self.chk_enable_finish.setChecked(bool(en_fin))

        use_spd = getattr(self.obj, "UseSpeederForFinishing", False)
        self.chk_use_speeder.setChecked(bool(use_spd))

        core = getattr(self.obj, "InscribedCoreType", "NONE")
        c_cov = getattr(self.obj, "InscribedCoverage", 0.0)
        self.lbl_status.setText(f"Detected Core: {core} (Coverage: {c_cov * 100.0:.1f}%)")

    def accept(self) -> bool:
        if not self.obj:
            return True

        self.obj.StartDepth = self.spin_start_z.value()
        self.obj.FinalDepth = self.spin_final_z.value()
        self.obj.RoughStepDown = self.spin_rough_stepdown.value()
        self.obj.FinishStepDown = self.spin_finish_stepdown.value()
        self.obj.FinishAllowance = self.spin_finish_allowance.value()
        self.obj.InscribedMinCoverage = self.spin_coverage_threshold.value()
        self.obj.PocketStrategy = self.combo_strategy.currentText()
        self.obj.RoughCycle = self.combo_rough_cycle.currentText()
        self.obj.FinishCycle = self.combo_finish_cycle.currentText()
        self.obj.EnableFinishing = self.chk_enable_finish.isChecked()
        self.obj.UseSpeederForFinishing = self.chk_use_speeder.isChecked()

        r_tool = self.combo_rough_tool.currentData()
        if r_tool:
            self.obj.RoughingTool = r_tool
        f_tool = self.combo_finish_tool.currentData()
        if f_tool:
            self.obj.FinishingTool = f_tool

        if hasattr(self.obj, "Proxy") and hasattr(self.obj.Proxy, "execute"):
            self.obj.Proxy.execute(self.obj)

        if App and App.ActiveDocument and hasattr(App.ActiveDocument, "recompute"):
            App.ActiveDocument.recompute()

        return True

    def reject(self) -> bool:
        return True
