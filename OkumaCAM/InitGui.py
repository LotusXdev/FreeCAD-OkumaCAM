"""OkumaCAM GUI Initialization and Workbench/Command Registration.

Registers PySide6 GUI commands, menus, toolbars, and preference pages
for Okuma OSP post-processing in FreeCAD.
"""

from __future__ import annotations

import os
import sys

try:
    _mod_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _mod_dir = os.path.abspath(".")
    for p in sys.path:
        if os.path.exists(os.path.join(p, "OkumaOSP_post.py")):
            _mod_dir = p
            break

if _mod_dir not in sys.path:
    sys.path.insert(0, _mod_dir)


import FreeCAD as App

try:
    import FreeCADGui as Gui
except ImportError:
    Gui = None

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    QtWidgets = None
    QtCore = None
    QtGui = None


class CommandExportOkumaOSP:
    """FreeCAD GUI Command to post-process active Job for Okuma OSP."""

    def GetResources(self) -> dict:
        icon_path = os.path.join(_mod_dir, "Gui", "Resources", "okuma_cam.svg")
        return {
            "Pixmap": icon_path if os.path.exists(icon_path) else "Path-PostProcess",
            "MenuText": "Export Okuma OSP G-Code...",
            "ToolTip": "Export active CAM Job to size-optimized Okuma OSP (.MIN / .SUB) G-code",
            "Accel": "Ctrl+Shift+O",
        }

    def IsActive(self) -> bool:
        if not App.ActiveDocument:
            return False
        # Active if there is at least one Path Job or feature
        for obj in App.ActiveDocument.Objects:
            if hasattr(obj, "Path"):
                return True
        return False

    def Activated(self) -> None:
        if not App.ActiveDocument or QtWidgets is None:
            return

        doc = App.ActiveDocument
        jobs = [obj for obj in doc.Objects if hasattr(obj, "Proxy") and getattr(obj.Proxy, "Type", "") == "Job"]

        target_obj = jobs[0] if jobs else None
        if not target_obj:
            # Fall back to any object with a Path
            path_objs = [obj for obj in doc.Objects if hasattr(obj, "Path")]
            if not path_objs:
                QtWidgets.QMessageBox.warning(
                    None,
                    "No CAM Job Found",
                    "No CAM Job or toolpath operations found in active document.",
                )
                return
            target_obj = path_objs[0]

        default_name = f"{doc.Label or 'OkumaJob'}.MIN"
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            None,
            "Export Okuma OSP Program",
            default_name,
            "Okuma Main Program (*.MIN *.min);;All Files (*.*)",
        )

        if not file_path:
            return

        import OkumaOSP_post
        try:
            res = OkumaOSP_post.export([target_obj], filename=file_path)
            if hasattr(res, "files_written") and res.files_written:
                msg = "Successfully exported Okuma OSP file(s):\n" + "\n".join(f"• {p}" for p in res.files_written)
            else:
                msg = f"Successfully exported Okuma OSP program to:\n{file_path}"
                if len(res) > 1 and res[1]:
                    sub_path = os.path.splitext(file_path)[0] + ".SUB"
                    msg += f"\n\nSubprogram written to:\n{sub_path}"
            QtWidgets.QMessageBox.information(None, "OkumaCAM Export Complete", msg)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                None, "Export Error", f"Error during Okuma OSP export:\n{str(exc)}"
            )


class CommandOkumaCAMPreferences:
    """FreeCAD GUI Command to open OkumaCAM settings dialog."""

    def GetResources(self) -> dict:
        icon_path = os.path.join(_mod_dir, "Gui", "Resources", "okuma_cam.svg")
        return {
            "Pixmap": icon_path if os.path.exists(icon_path) else "Path-Preferences",
            "MenuText": "Okuma OSP Settings...",
            "ToolTip": "Configure Okuma OSP post-processor, macro G111, and cycle options",
        }

    def IsActive(self) -> bool:
        return True

    def Activated(self) -> None:
        if QtWidgets is None:
            return
        from Gui.Preferences import OkumaCAMPreferencesPage
        dlg = QtWidgets.QDialog()
        dlg.setWindowTitle("OkumaCAM Settings")
        layout = QtWidgets.QVBoxLayout(dlg)
        pref_page = OkumaCAMPreferencesPage(dlg)
        layout.addWidget(pref_page.form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel, dlg
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() == QtWidgets.QDialog.Accepted:
            pref_page.saveSettings()


class CommandCreateContourPocket:
    """FreeCAD GUI Command to create an OkumaContourPocket operation."""

    def GetResources(self) -> dict:
        icon_path = os.path.join(_mod_dir, "Gui", "Resources", "okuma_pocket.svg")
        return {
            "Pixmap": icon_path if os.path.exists(icon_path) else "Path-Pocket",
            "MenuText": "Contour Pocket (Okuma)...",
            "ToolTip": "Create Okuma-optimized contour pocket with inscribed volume canned cycle & residual subprogram",
        }

    def IsActive(self) -> bool:
        return bool(App.ActiveDocument)

    def Activated(self) -> None:
        if not App.ActiveDocument:
            return
        from OkumaCAM.Op.ContourPocket import Create as CreateContourPocket
        op = CreateContourPocket()
        if Gui and hasattr(Gui, "Control"):
            from OkumaCAM.Gui.TaskPanelContourPocket import TaskPanelContourPocket
            panel = TaskPanelContourPocket(op)
            Gui.Control.showDialog(panel)


class CommandCreateContourSurfacing:
    """FreeCAD GUI Command to create an OkumaContourSurfacing operation."""

    def GetResources(self) -> dict:
        icon_path = os.path.join(_mod_dir, "Gui", "Resources", "okuma_surface.svg")
        return {
            "Pixmap": icon_path if os.path.exists(icon_path) else "Path-Face",
            "MenuText": "Contour Surfacing (Okuma)...",
            "ToolTip": "Create Okuma-optimized contour surfacing operation with native face milling (FMILR/FMILF)",
        }

    def IsActive(self) -> bool:
        return bool(App.ActiveDocument)

    def Activated(self) -> None:
        if not App.ActiveDocument:
            return
        from OkumaCAM.Op.ContourSurfacing import Create as CreateContourSurfacing
        op = CreateContourSurfacing()
        if Gui and hasattr(Gui, "Control"):
            from OkumaCAM.Gui.TaskPanelContourSurfacing import TaskPanelContourSurfacing
            panel = TaskPanelContourSurfacing(op)
            Gui.Control.showDialog(panel)


if Gui and getattr(App, "GuiUp", 0) and hasattr(Gui, "Workbench"):
    class OkumaCAMWorkbench(Gui.Workbench):
        """OkumaCAM Add-on Workbench for FreeCAD."""

        MenuText = "OkumaCAM"
        ToolTip = "Okuma OSP CAM Optimization and Post-Processing Workbench"
        icon_path = os.path.join(_mod_dir, "Gui", "Resources", "okuma_cam.svg")
        Icon = icon_path if os.path.exists(icon_path) else ""

        def Initialize(self) -> None:
            commands = [
                "OkumaCAM_ContourPocket",
                "OkumaCAM_ContourSurfacing",
                "OkumaCAM_Export",
                "OkumaCAM_Preferences",
            ]
            self.appendToolbar("OkumaCAM", commands)
            self.appendMenu("OkumaCAM", commands)

        def GetClassName(self) -> str:
            return "Gui::PythonWorkbench"

    # Register GUI commands and workbench
    if hasattr(Gui, "addCommand"):
        Gui.addCommand("OkumaCAM_ContourPocket", CommandCreateContourPocket())
        Gui.addCommand("OkumaCAM_ContourSurfacing", CommandCreateContourSurfacing())
        Gui.addCommand("OkumaCAM_Export", CommandExportOkumaOSP())
        Gui.addCommand("OkumaCAM_Preferences", CommandOkumaCAMPreferences())
    if hasattr(Gui, "addWorkbench"):
        Gui.addWorkbench(OkumaCAMWorkbench())

