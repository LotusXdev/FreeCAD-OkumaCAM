"""Headless PySide6 tests for OkumaCAM Preferences interface."""

from __future__ import annotations

import sys
import unittest
from PySide6 import QtWidgets
import FreeCAD as App
try:
    from OkumaCAM.Gui.Preferences import OkumaCAMPreferencesPage
except ImportError:
    from Gui.Preferences import OkumaCAMPreferencesPage


class TestOkumaCAMPreferences(unittest.TestCase):
    """Test cases for Preferences page widget creation and state persistence."""

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    def setUp(self):
        self._reset_params()

    def tearDown(self):
        self._reset_params()

    def _reset_params(self):
        pref = OkumaCAMPreferencesPage()
        pref.combo_controller.setCurrentText("OSP-P300")
        pref.chk_toolcheck.setChecked(False)
        pref.chk_subprograms.setChecked(False)
        pref.spin_precision.setValue(4)
        pref.chk_speeder.setChecked(False)
        pref.combo_speeder_scope.setCurrentText("Finishing Operations Only")
        pref.chk_speeder_dual_m00.setChecked(True)
        pref.chk_speeder_verify.setChecked(True)
        pref.spin_speeder_retract.setValue(200.0)
        pref.chk_separate_rf.setChecked(False)
        pref.edit_rough_suffix.setText("_ROUGH")
        pref.edit_finish_suffix.setText("_FINISH")
        pref.saveSettings()

    def test_preferences_instantiation(self):
        """Verify Preferences page builds all UI controls correctly."""
        pref = OkumaCAMPreferencesPage()
        self.assertIsNotNone(pref.form)
        self.assertEqual(pref.combo_controller.count(), 5)
        self.assertTrue(pref.chk_toolcheck.text().startswith("Enable G111 Tool Check"))
        self.assertTrue(pref.chk_native_cycles.isChecked())
        self.assertTrue(pref.chk_patterns.isChecked())

        # Electric Speeder controls
        self.assertIsNotNone(pref.chk_speeder)
        self.assertEqual(pref.combo_speeder_scope.count(), 3)
        self.assertTrue(pref.chk_speeder_dual_m00.isChecked())
        self.assertTrue(pref.chk_speeder_verify.isChecked())
        self.assertEqual(pref.spin_speeder_retract.value(), 200.0)

        # Separate Rough/Finish controls
        self.assertIsNotNone(pref.chk_separate_rf)
        self.assertEqual(pref.edit_rough_suffix.text(), "_ROUGH")
        self.assertEqual(pref.edit_finish_suffix.text(), "_FINISH")

    def test_preferences_save_and_load(self):
        """Verify round-trip save and load into FreeCAD BaseApp parameter group."""
        pref = OkumaCAMPreferencesPage()

        try:
            # Modify values
            pref.combo_controller.setCurrentText("OSP-P500")
            pref.chk_toolcheck.setChecked(True)
            pref.chk_subprograms.setChecked(True)
            pref.spin_precision.setValue(5)
            pref.chk_speeder.setChecked(True)
            pref.combo_speeder_scope.setCurrentText("All Operations")
            pref.chk_speeder_dual_m00.setChecked(False)
            pref.chk_speeder_verify.setChecked(True)
            pref.spin_speeder_retract.setValue(250.0)
            pref.chk_separate_rf.setChecked(True)
            pref.edit_rough_suffix.setText("_ROUGHING")
            pref.edit_finish_suffix.setText("_FINISHING")
            pref.saveSettings()

            # Create new instance and load
            pref2 = OkumaCAMPreferencesPage()
            pref2.loadSettings()

            self.assertEqual(pref2.combo_controller.currentText(), "OSP-P500")
            self.assertTrue(pref2.chk_toolcheck.isChecked())
            self.assertTrue(pref2.chk_subprograms.isChecked())
            self.assertEqual(pref2.spin_precision.value(), 5)
            self.assertTrue(pref2.chk_speeder.isChecked())
            self.assertEqual(pref2.combo_speeder_scope.currentText(), "All Operations")
            self.assertFalse(pref2.chk_speeder_dual_m00.isChecked())
            self.assertTrue(pref2.chk_speeder_verify.isChecked())
            self.assertEqual(pref2.spin_speeder_retract.value(), 250.0)
            self.assertTrue(pref2.chk_separate_rf.isChecked())
            self.assertEqual(pref2.edit_rough_suffix.text(), "_ROUGHING")
            self.assertEqual(pref2.edit_finish_suffix.text(), "_FINISHING")
        finally:
            self._reset_params()


def _load_init_gui():
    """Load OkumaCAM's InitGui module without sys.path collision from other workbenches."""
    import importlib.util
    import os
    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    init_gui_file = os.path.join(pkg_dir, "InitGui.py")
    spec = importlib.util.spec_from_file_location("OkumaCAM_InitGui_Test", init_gui_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod



class TestOkumaCAMGuiCommands(unittest.TestCase):
    """Test cases for InitGui commands and workbench definition."""

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    def setUp(self):
        self.doc = App.newDocument("GuiTestDoc")
        self.init_gui = _load_init_gui()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_command_export_resources_and_active_state(self):
        """Verify CommandExportOkumaOSP resources and context-sensitive activation."""
        cmd = self.init_gui.CommandExportOkumaOSP()

        # Resources check
        res = cmd.GetResources()
        self.assertIn("Export Okuma OSP G-Code...", res["MenuText"])
        self.assertIn("ToolTip", res)
        self.assertEqual(res.get("Accel"), "Ctrl+Shift+O")

        # Inactive when document has no Path objects
        self.assertFalse(cmd.IsActive())

        # Active once a Path object is present
        import Path
        feat = self.doc.addObject("Path::Feature", "TestPathObj")
        feat.Path = Path.Path()
        self.assertTrue(cmd.IsActive())

    def test_command_preferences_resources(self):
        """Verify CommandOkumaCAMPreferences resources and activation."""
        cmd = self.init_gui.CommandOkumaCAMPreferences()

        res = cmd.GetResources()
        self.assertIn("Okuma OSP Settings...", res["MenuText"])
        self.assertIn("ToolTip", res)
        self.assertTrue(cmd.IsActive())

    def test_command_contour_pocket_resources(self):
        """Verify CommandCreateContourPocket resources and activation."""
        cmd = self.init_gui.CommandCreateContourPocket()
        res = cmd.GetResources()
        self.assertIn("Contour Pocket (Okuma)...", res["MenuText"])
        self.assertIn("ToolTip", res)
        self.assertTrue(cmd.IsActive())

    def test_command_contour_surfacing_resources(self):
        """Verify CommandCreateContourSurfacing resources and activation."""
        cmd = self.init_gui.CommandCreateContourSurfacing()
        res = cmd.GetResources()
        self.assertIn("Contour Surfacing (Okuma)...", res["MenuText"])
        self.assertIn("ToolTip", res)
        self.assertTrue(cmd.IsActive())

    def test_task_panels_instantiation(self):
        try:
            from OkumaCAM.Op.ContourPocket import Create as CreatePocket
            from OkumaCAM.Op.ContourSurfacing import Create as CreateSurfacing
            from OkumaCAM.Gui.TaskPanelContourPocket import TaskPanelContourPocket
            from OkumaCAM.Gui.TaskPanelContourSurfacing import TaskPanelContourSurfacing
        except ImportError:
            from Op.ContourPocket import Create as CreatePocket
            from Op.ContourSurfacing import Create as CreateSurfacing
            from Gui.TaskPanelContourPocket import TaskPanelContourPocket
            from Gui.TaskPanelContourSurfacing import TaskPanelContourSurfacing

        pocket_op = CreatePocket("TestPocketUI")
        pocket_panel = TaskPanelContourPocket(pocket_op)
        if QtWidgets and QtWidgets.QApplication.instance():
            self.assertIsNotNone(pocket_panel.form)
            self.assertIsNotNone(pocket_panel.chk_use_speeder)
            pocket_panel.chk_use_speeder.setChecked(True)
        self.assertTrue(pocket_panel.accept())
        self.assertTrue(getattr(pocket_op, "UseSpeederForFinishing", False))

        surf_op = CreateSurfacing("TestSurfUI")
        surf_panel = TaskPanelContourSurfacing(surf_op)
        if QtWidgets and QtWidgets.QApplication.instance():
            self.assertIsNotNone(surf_panel.form)
            self.assertIsNotNone(surf_panel.chk_use_speeder)
            surf_panel.chk_use_speeder.setChecked(True)
        self.assertTrue(surf_panel.accept())
        self.assertTrue(getattr(surf_op, "UseSpeederForFinishing", False))

    def test_workbench_definition(self):
        """Verify OkumaCAMWorkbench metadata and initialization if GUI is active."""
        if hasattr(self.init_gui, "OkumaCAMWorkbench"):
            wb = self.init_gui.OkumaCAMWorkbench()
            self.assertEqual(wb.MenuText, "OkumaCAM")
            self.assertEqual(wb.GetClassName(), "Gui::PythonWorkbench")
            wb.Initialize()
        else:
            # Expected in headless / CLI mode where App.GuiUp is 0
            self.assertFalse(getattr(App, "GuiUp", 0))




if __name__ == "__main__":
    unittest.main()

