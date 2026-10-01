"""OkumaCAM TaskPanel for Contour Surfacing Operation."""

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


class TaskPanelContourSurfacing:
    """TaskPanel dialog for configuring OkumaContourSurfacing operations."""

    def __init__(self, obj: Any) -> None:
        self.obj = obj
        has_app = QtWidgets is not None and QtWidgets.QApplication.instance() is not None
        self.form = QtWidgets.QWidget() if has_app else None
        if self.form:
            self._setup_ui()
            self._load_from_obj()

    def _setup_ui(self) -> None:
        self.form.setWindowTitle("Okuma Contour Surfacing Settings")
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
        self.spin_finish_stepdown.setValue(0.5)
        self.spin_finish_stepdown.setSuffix(" mm")

        depth_layout.addRow("Start Depth:", self.spin_start_z)
        depth_layout.addRow("Final Depth:", self.spin_final_z)
        depth_layout.addRow("Rough Stepdown (Q):", self.spin_rough_stepdown)
        depth_layout.addRow("Finish Stepdown:", self.spin_finish_stepdown)
        layout.addWidget(depth_grp)

        # 3. Strategy Group
        strat_grp = QtWidgets.QGroupBox("Surfacing Strategy")
        strat_layout = QtWidgets.QFormLayout(strat_grp)

        self.combo_strategy = QtWidgets.QComboBox()
        self.combo_strategy.addItems(["Auto", "CannedCycle (FMILR/FMILF)", "Waterline Subprogram", "Standard"])

        self.combo_facing_pattern = QtWidgets.QComboBox()
        self.combo_facing_pattern.addItems(["Zigzag (FMILR)", "Parallel (FMILF)"])

        self.spin_rough_stepover = QtWidgets.QDoubleSpinBox()
        self.spin_rough_stepover.setRange(1.0, 100.0)
        self.spin_rough_stepover.setValue(75.0)
        self.spin_rough_stepover.setSuffix(" %")

        self.spin_finish_stepover = QtWidgets.QDoubleSpinBox()
        self.spin_finish_stepover.setRange(1.0, 100.0)
        self.spin_finish_stepover.setValue(50.0)
        self.spin_finish_stepover.setSuffix(" %")

        self.spin_finish_allowance = QtWidgets.QDoubleSpinBox()
        self.spin_finish_allowance.setRange(0.0, 50.0)
        self.spin_finish_allowance.setValue(0.25)
        self.spin_finish_allowance.setSuffix(" mm")

        strat_layout.addRow("Strategy Selection:", self.combo_strategy)
        strat_layout.addRow("Facing Pattern:", self.combo_facing_pattern)
        strat_layout.addRow("Rough Stepover (P):", self.spin_rough_stepover)
        strat_layout.addRow("Finish Stepover:", self.spin_finish_stepover)
        strat_layout.addRow("Finish Stock (K):", self.spin_finish_allowance)
        layout.addWidget(strat_grp)

        # 4. Diagnostics Group
        diag_grp = QtWidgets.QGroupBox("Surface Diagnostics")
        diag_layout = QtWidgets.QVBoxLayout(diag_grp)
        self.lbl_surface_type = QtWidgets.QLabel("Surface Geometry: Planar Face (FMILR/FMILF Eligible)")
        self.lbl_surface_type.setStyleSheet("font-weight: bold; color: #059669;")
        diag_layout.addWidget(self.lbl_surface_type)
        layout.addWidget(diag_grp)

        layout.addStretch()

    def _populate_tools(self) -> None:
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
        self.spin_final_z.setValue(_val("FinalDepth", -5.0))
        self.spin_rough_stepdown.setValue(_val("RoughStepDown", 2.0))
        self.spin_finish_stepdown.setValue(_val("FinishStepDown", 0.5))
        self.spin_rough_stepover.setValue(_val("RoughStepOver", 75.0))
        self.spin_finish_stepover.setValue(_val("FinishStepOver", 50.0))
        self.spin_finish_allowance.setValue(_val("FinishAllowance", 0.25))

        strat = getattr(self.obj, "SurfacingStrategy", "Auto")
        idx = self.combo_strategy.findText(str(strat))
        if idx >= 0:
            self.combo_strategy.setCurrentIndex(idx)

        en_fin = getattr(self.obj, "EnableFinishing", True)
        self.chk_enable_finish.setChecked(bool(en_fin))

        use_spd = getattr(self.obj, "UseSpeederForFinishing", False)
        self.chk_use_speeder.setChecked(bool(use_spd))

        is_pl = getattr(self.obj, "IsPlanarFace", True)
        if is_pl:
            self.lbl_surface_type.setText("Surface Geometry: Planar Face (FMILR/FMILF)")
            self.lbl_surface_type.setStyleSheet("font-weight: bold; color: #059669;")
        else:
            self.lbl_surface_type.setText("Surface Geometry: 3D Contoured Surface (Waterline Subprogram)")
            self.lbl_surface_type.setStyleSheet("font-weight: bold; color: #0284c7;")

    def accept(self) -> bool:
        if not self.obj:
            return True

        self.obj.StartDepth = self.spin_start_z.value()
        self.obj.FinalDepth = self.spin_final_z.value()
        self.obj.RoughStepDown = self.spin_rough_stepdown.value()
        self.obj.FinishStepDown = self.spin_finish_stepdown.value()
        self.obj.RoughStepOver = self.spin_rough_stepover.value()
        self.obj.FinishStepOver = self.spin_finish_stepover.value()
        self.obj.FinishAllowance = self.spin_finish_allowance.value()
        self.obj.SurfacingStrategy = self.combo_strategy.currentText()
        self.obj.FacingPattern = self.combo_facing_pattern.currentText()
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
