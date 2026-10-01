"""Okuma Contour Surfacing Operation.

Implements Okuma-optimized surfacing with dual-tool roughing and finishing,
native face milling canned cycles (FMILR, FMILF), and 3D waterline subprograms.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import FreeCAD as App
except ImportError:
    App = None

try:
    import Path
except ImportError:
    Path = None


class ContourSurfacing:
    """FreeCAD Path operation proxy for Okuma-optimized contour surfacing."""

    Type = "OkumaContourSurfacing"

    def __init__(self, obj: Any) -> None:
        self.Type = "OkumaContourSurfacing"
        obj.Proxy = self
        self.is_planar_face: bool = True
        self.face_bounds: Dict[str, float] = {}
        self.initProperties(obj)

    def initProperties(self, obj: Any) -> None:
        """Initialize FreeCAD object properties with standard types."""
        def _add_prop(prop_type: str, name: str, group: str, doc: str, default: Any = None):
            if hasattr(obj, name):
                return
            if hasattr(obj, "addProperty"):
                obj.addProperty(prop_type, name, group, doc)
                if default is not None:
                    try:
                        setattr(obj, name, default)
                    except Exception:
                        pass
            else:
                setattr(obj, name, default)

        # Base geometry
        _add_prop("App::PropertyLinkSubList", "Base", "Base", "Base faces or surfaces to machine")

        # Tool Controllers (Dual Tool Strategy)
        _add_prop("App::PropertyLink", "RoughingTool", "Tool", "Tool controller for roughing pass")
        _add_prop("App::PropertyLink", "FinishingTool", "Tool", "Tool controller for finishing pass")
        _add_prop("App::PropertyBool", "EnableFinishing", "Tool", "Execute finishing pass with FinishingTool", True)
        _add_prop("App::PropertyBool", "UseSpeederForFinishing", "Tool", "Use electric spindle speeder for finishing pass", False)

        # Depths
        _add_prop("App::PropertyDistance", "StartDepth", "Depth", "Starting top stock level", 0.0)
        _add_prop("App::PropertyDistance", "FinalDepth", "Depth", "Final surface depth", -5.0)
        _add_prop("App::PropertyDistance", "RoughStepDown", "Depth", "Axial depth per cut for roughing (Q)", 2.0)
        _add_prop("App::PropertyDistance", "FinishStepDown", "Depth", "Axial depth per cut for finishing (Q)", 0.5)

        # Stepover & Stock Allowance
        _add_prop("App::PropertyFloat", "RoughStepOver", "Strategy", "Roughing stepover percentage (P)", 75.0)
        _add_prop("App::PropertyFloat", "FinishStepOver", "Strategy", "Finishing stepover percentage", 50.0)
        _add_prop("App::PropertyDistance", "FinishAllowance", "Strategy", "Finish allowance K left on surface", 0.25)

        # Strategy Selection
        if not hasattr(obj, "SurfacingStrategy"):
            if hasattr(obj, "addProperty"):
                obj.addProperty("App::PropertyEnumeration", "SurfacingStrategy", "Strategy", "Machining strategy selection")
                obj.SurfacingStrategy = ["Auto", "CannedCycle (FMILR/FMILF)", "Waterline Subprogram", "Standard"]
                obj.SurfacingStrategy = "Auto"
            else:
                setattr(obj, "SurfacingStrategy", "Auto")

        if not hasattr(obj, "FacingPattern"):
            if hasattr(obj, "addProperty"):
                obj.addProperty("App::PropertyEnumeration", "FacingPattern", "Strategy", "Face milling cut pattern")
                obj.FacingPattern = ["Zigzag (FMILR)", "Parallel (FMILF)"]
                obj.FacingPattern = "Zigzag (FMILR)"
            else:
                setattr(obj, "FacingPattern", "Zigzag (FMILR)")

        # Analysis Output
        _add_prop("App::PropertyBool", "IsPlanarFace", "Analysis", "Whether target surface is a planar face", True)
        _add_prop("App::PropertyString", "FaceParams", "Analysis", "Face dimensions and position", "")

    def onDocumentRestored(self, obj: Any) -> None:
        self.initProperties(obj)

    def _extract_surface_info(self, obj: Any) -> Tuple[bool, float, float, float, float, float, float]:
        """Extract bounds (is_planar, xmin, ymin, xlen, ylen, zmin, zmax)."""
        if hasattr(self, "mock_bounds") and self.mock_bounds:
            mb = self.mock_bounds
            return (
                mb.get("is_planar", True),
                mb.get("xmin", 0.0),
                mb.get("ymin", 0.0),
                mb.get("xlen", 100.0),
                mb.get("ylen", 50.0),
                mb.get("zmin", -5.0),
                mb.get("zmax", 0.0),
            )

        is_planar = True
        strat = str(getattr(obj, "SurfacingStrategy", "Auto"))
        if strat == "Waterline Subprogram":
            is_planar = False
        elif hasattr(obj, "IsPlanar"):
            is_planar = bool(obj.IsPlanar)

        if hasattr(obj, "Shape") and hasattr(obj.Shape, "BoundBox"):
            bb = obj.Shape.BoundBox
            return (is_planar, bb.XMin, bb.YMin, bb.XLength, bb.YLength, bb.ZMin, bb.ZMax)

        # Default fallback planar bounds
        return (is_planar, 0.0, 0.0, 100.0, 50.0, -5.0, 0.0)

    def execute(self, obj: Any) -> None:
        """Execute surface analysis and generate visual simulation paths."""
        is_planar, xmin, ymin, xlen, ylen, zmin, zmax = self._extract_surface_info(obj)
        self.is_planar_face = is_planar

        def _val(attr_name: str, fallback: float) -> float:
            v = getattr(obj, attr_name, fallback)
            return float(getattr(v, "Value", v))

        start_z = _val("StartDepth", zmax)
        final_z = _val("FinalDepth", zmin)
        r_stepdown = _val("RoughStepDown", 2.0)

        obj.IsPlanarFace = is_planar
        self.face_bounds = {
            "is_planar": is_planar,
            "xmin": xmin,
            "ymin": ymin,
            "xlen": xlen,
            "ylen": ylen,
            "zmin": final_z,
            "zmax": start_z,
        }
        obj.FaceParams = json.dumps(self.face_bounds)

        # Construct visual Path commands
        if Path and hasattr(Path, "Command") and hasattr(Path, "Path"):
            cmds = []
            cmds.append(Path.Command("G0", {"Z": start_z + 5.0}))

            if is_planar:
                # Zigzag facing strokes
                cur_z = start_z - r_stepdown
                while cur_z >= final_z - 1e-4:
                    cmds.append(Path.Command("G0", {"X": xmin, "Y": ymin}))
                    cmds.append(Path.Command("G1", {"Z": cur_z, "F": 150.0}))
                    y_cur = ymin
                    step = max(5.0, ylen * (_val("RoughStepOver", 75.0) / 100.0) / 2.0)
                    dir_x = 1
                    while y_cur <= ymin + ylen + 1e-4:
                        x_target = (xmin + xlen) if dir_x == 1 else xmin
                        cmds.append(Path.Command("G1", {"X": x_target, "Y": y_cur, "F": 450.0}))
                        y_cur += step
                        dir_x = -dir_x
                        if y_cur <= ymin + ylen:
                            cmds.append(Path.Command("G1", {"Y": y_cur, "F": 450.0}))
                    cur_z -= r_stepdown
            else:
                # 3D contour sweep strokes
                cmds.append(Path.Command("G0", {"X": xmin, "Y": ymin}))
                cmds.append(Path.Command("G1", {"Z": final_z, "F": 150.0}))
                cmds.append(Path.Command("G1", {"X": xmin + xlen, "Y": ymin + ylen, "F": 350.0}))

            cmds.append(Path.Command("G0", {"Z": start_z + 10.0}))
            try:
                obj.Path = Path.Path(cmds)
            except Exception:
                pass

    @classmethod
    def Create(cls, name: str = "OkumaContourSurfacing", obj: Any = None, parentJob: Any = None) -> Any:
        return Create(name=name, obj=obj, parentJob=parentJob)


def Create(name: str = "OkumaContourSurfacing", obj: Any = None, parentJob: Any = None) -> Any:
    """Factory function to create a new OkumaContourSurfacing operation."""
    if obj is None:
        if App and hasattr(App, "ActiveDocument") and App.ActiveDocument:
            doc = App.ActiveDocument
            obj = doc.addObject("Path::FeaturePython", name)
        else:
            class MockOpObject:
                def __init__(self, obj_name: str) -> None:
                    self.Name = obj_name
                    self.Label = obj_name
                    self.Proxy = None
            obj = MockOpObject(name)

    proxy = ContourSurfacing(obj)
    if parentJob and hasattr(parentJob, "Operations") and hasattr(parentJob.Operations, "addObject"):
        parentJob.Operations.addObject(obj)
    return obj
