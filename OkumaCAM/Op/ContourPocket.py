"""Okuma Contour Pocket Operation.

Implements Okuma-optimized pocketing with dual-tool roughing and finishing,
inscribed volume canned cycles (PMIL, PMILR, circular cycles), and residual
margin subprograms.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import FreeCAD as App
except ImportError:
    App = None

try:
    import Path
except ImportError:
    Path = None

try:
    from OkumaCAM.InscribedVolume import (
        InscribedCircle,
        InscribedRectangle,
        InscribedResult,
        InscribedVolumeAnalyzer,
    )
except ImportError:
    from InscribedVolume import (
        InscribedCircle,
        InscribedRectangle,
        InscribedResult,
        InscribedVolumeAnalyzer,
    )


class ContourPocket:
    """FreeCAD Path operation proxy for Okuma-optimized contour pocketing."""

    Type = "OkumaContourPocket"

    def __init__(self, obj: Any) -> None:
        self.Type = "OkumaContourPocket"
        obj.Proxy = self
        self.residual_commands: List[Tuple[str, Dict[str, float]]] = []
        self.analysis_result: Optional[InscribedResult] = None
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
        _add_prop("App::PropertyLinkSubList", "Base", "Base", "Base faces, sketches or edges")

        # Tool Controllers (Dual Tool Strategy)
        _add_prop("App::PropertyLink", "RoughingTool", "Tool", "Tool controller for roughing pass")
        _add_prop("App::PropertyLink", "FinishingTool", "Tool", "Tool controller for finishing pass")
        _add_prop("App::PropertyBool", "EnableFinishing", "Tool", "Execute finishing pass with FinishingTool", True)
        _add_prop("App::PropertyBool", "UseSpeederForFinishing", "Tool", "Use electric spindle speeder for finishing pass", False)

        # Depths
        _add_prop("App::PropertyDistance", "StartDepth", "Depth", "Starting Z clearance / top of pocket", 0.0)
        _add_prop("App::PropertyDistance", "FinalDepth", "Depth", "Final bottom Z level of pocket", -10.0)
        _add_prop("App::PropertyDistance", "RoughStepDown", "Depth", "Axial depth per cut for roughing (Q)", 2.0)
        _add_prop("App::PropertyDistance", "FinishStepDown", "Depth", "Axial depth per cut for finishing (Q)", 1.0)

        # Stepover & Stock Allowance
        _add_prop("App::PropertyFloat", "RoughStepOver", "Strategy", "Roughing stepover percentage (P)", 70.0)
        _add_prop("App::PropertyFloat", "FinishStepOver", "Strategy", "Finishing stepover percentage", 50.0)
        _add_prop("App::PropertyDistance", "FinishAllowance", "Strategy", "Finish allowance K left on walls and floor", 0.5)

        # Inscribed Volume Strategy
        if not hasattr(obj, "PocketStrategy"):
            if hasattr(obj, "addProperty"):
                obj.addProperty("App::PropertyEnumeration", "PocketStrategy", "Strategy", "Machining strategy selection")
                obj.PocketStrategy = ["Auto", "Force Canned Cycle", "Force Subprogram", "Standard"]
                obj.PocketStrategy = "Auto"
            else:
                setattr(obj, "PocketStrategy", "Auto")

        _add_prop(
            "App::PropertyFloat",
            "InscribedMinCoverage",
            "Strategy",
            "Minimum inscribed volume coverage ratio required to deploy canned cycle (0.0-1.0)",
            0.40,
        )

        if not hasattr(obj, "RoughCycle"):
            if hasattr(obj, "addProperty"):
                obj.addProperty("App::PropertyEnumeration", "RoughCycle", "Strategy", "Okuma roughing cycle type")
                obj.RoughCycle = ["PMILR (Spiral)", "PMIL (Zigzag)"]
                obj.RoughCycle = "PMILR (Spiral)"
            else:
                setattr(obj, "RoughCycle", "PMILR (Spiral)")

        if not hasattr(obj, "FinishCycle"):
            if hasattr(obj, "addProperty"):
                obj.addProperty("App::PropertyEnumeration", "FinishCycle", "Strategy", "Okuma finishing cycle type")
                obj.FinishCycle = ["RMILI (Perimeter)", "Contour Sweep"]
                obj.FinishCycle = "RMILI (Perimeter)"
            else:
                setattr(obj, "FinishCycle", "RMILI (Perimeter)")

        # Draft / Tapered Walls
        _add_prop("App::PropertyAngle", "DraftAngle", "Draft", "Wall draft angle in degrees", 0.0)
        if not hasattr(obj, "DraftMode"):
            if hasattr(obj, "addProperty"):
                obj.addProperty("App::PropertyEnumeration", "DraftMode", "Draft", "Macro draft expansion method")
                obj.DraftMode = ["None", "Scale (G51)", "Offset (PR)"]
                obj.DraftMode = "None"
            else:
                setattr(obj, "DraftMode", "None")

        # Output / Analysis Results
        _add_prop("App::PropertyString", "InscribedCoreType", "Analysis", "Detected inscribed core type", "NONE")
        _add_prop("App::PropertyFloat", "InscribedCoverage", "Analysis", "Detected inscribed coverage ratio", 0.0)
        _add_prop("App::PropertyString", "InscribedParams", "Analysis", "Parameters of inscribed core", "")

    def onDocumentRestored(self, obj: Any) -> None:
        self.initProperties(obj)

    def _extract_boundary(self, obj: Any) -> List[Tuple[float, float]]:
        """Extract 2D polygon vertices from object base geometry."""
        # 1. Custom mock boundary points if provided in proxy or object
        if hasattr(self, "boundary_points") and self.boundary_points:
            return list(self.boundary_points)
        if hasattr(obj, "BoundaryPoints") and obj.BoundaryPoints:
            return list(obj.BoundaryPoints)

        # 2. Extract from Base if present
        if hasattr(obj, "Base") and obj.Base:
            try:
                base_objs = obj.Base if isinstance(obj.Base, (list, tuple)) else [obj.Base]
                for b in base_objs:
                    target = b[0] if isinstance(b, tuple) else b
                    if hasattr(target, "Shape") and hasattr(target.Shape, "Wires"):
                        for wire in target.Shape.Wires:
                            pts = [(v.X, v.Y) for v in wire.OrderedVertexes]
                            if len(pts) >= 3:
                                return pts
            except Exception:
                pass

        # 3. Extract from Shape bounding box
        if hasattr(obj, "Shape") and hasattr(obj.Shape, "BoundBox"):
            bb = obj.Shape.BoundBox
            return [
                (bb.XMin, bb.YMin),
                (bb.XMax, bb.YMin),
                (bb.XMax, bb.YMax),
                (bb.XMin, bb.YMax),
            ]

        # 4. Default fallback rectangle
        return [(0.0, 0.0), (100.0, 0.0), (100.0, 60.0), (0.0, 60.0)]

    def _get_tool_diameter(self, obj: Any) -> float:
        """Resolve roughing tool cutter diameter."""
        tc = getattr(obj, "RoughingTool", None) or getattr(obj, "ToolController", None)
        if tc:
            if hasattr(tc, "Tool") and hasattr(tc.Tool, "Diameter"):
                try:
                    return float(getattr(tc.Tool.Diameter, "Value", tc.Tool.Diameter))
                except Exception:
                    pass
            if hasattr(tc, "Diameter"):
                try:
                    return float(getattr(tc.Diameter, "Value", tc.Diameter))
                except Exception:
                    pass
        return 10.0

    def execute(self, obj: Any) -> None:
        """Execute operation analysis and generate toolpath representation."""
        poly = self._extract_boundary(obj)
        tool_dia = self._get_tool_diameter(obj)

        def _val(attr_name: str, fallback: float) -> float:
            v = getattr(obj, attr_name, fallback)
            return float(getattr(v, "Value", v))

        start_z = _val("StartDepth", 0.0)
        final_z = _val("FinalDepth", -10.0)
        r_stepdown = _val("RoughStepDown", 2.0)
        allowance = _val("FinishAllowance", 0.5)
        min_cov = getattr(obj, "InscribedMinCoverage", 0.40)
        strategy_pref = str(getattr(obj, "PocketStrategy", "Auto"))

        # Run Inscribed Volume Analysis
        result = InscribedVolumeAnalyzer.analyze_pocket(
            boundary=poly,
            tool_diameter=tool_dia,
            finish_allowance=allowance,
            min_coverage=min_cov,
        )
        self.analysis_result = result

        # Apply strategy override
        effective_core = result.strategy
        if strategy_pref == "Force Subprogram" or strategy_pref == "Standard":
            effective_core = "NONE"

        obj.InscribedCoreType = effective_core
        obj.InscribedCoverage = result.coverage_ratio if effective_core != "NONE" else 0.0

        params: Dict[str, Any] = {}
        if effective_core == "RECTANGLE" and result.rectangle:
            params = {
                "type": "RECTANGLE",
                "xp": result.rectangle.xp,
                "yp": result.rectangle.yp,
                "idx": result.rectangle.idx,
                "jdy": result.rectangle.jdy,
                "width": result.rectangle.width,
                "height": result.rectangle.height,
                "area": result.rectangle.area,
            }
        elif effective_core == "CIRCLE" and result.circle:
            params = {
                "type": "CIRCLE",
                "xc": result.circle.center_x,
                "yc": result.circle.center_y,
                "radius": result.circle.radius,
                "area": result.circle.area,
            }
        obj.InscribedParams = json.dumps(params)

        # Generate residual clearing commands
        if effective_core != "NONE":
            self.residual_commands = InscribedVolumeAnalyzer.generate_residual_clearing_commands(
                boundary=poly,
                rec=result.rectangle if effective_core == "RECTANGLE" else None,
                circ=result.circle if effective_core == "CIRCLE" else None,
                tool_diameter=tool_dia,
                stepover_ratio=_val("RoughStepOver", 70.0) / 100.0,
            )
        else:
            self.residual_commands = []

        # Construct visual Path commands if Path module is active
        if Path and hasattr(Path, "Command") and hasattr(Path, "Path"):
            cmds = []
            cmds.append(Path.Command("G0", {"Z": start_z + 2.0}))

            # 1. Inscribed core visual path
            if effective_core == "RECTANGLE" and result.rectangle:
                rx = result.rectangle.xp
                ry = result.rectangle.yp
                rw = result.rectangle.idx
                rh = result.rectangle.jdy
                cur_z = start_z - r_stepdown
                while cur_z >= final_z - 1e-4:
                    cmds.append(Path.Command("G0", {"X": rx, "Y": ry}))
                    cmds.append(Path.Command("G1", {"Z": cur_z, "F": 100.0}))
                    cmds.append(Path.Command("G1", {"X": rx + rw, "Y": ry, "F": 250.0}))
                    cmds.append(Path.Command("G1", {"X": rx + rw, "Y": ry + rh, "F": 250.0}))
                    cmds.append(Path.Command("G1", {"X": rx, "Y": ry + rh, "F": 250.0}))
                    cmds.append(Path.Command("G1", {"X": rx, "Y": ry, "F": 250.0}))
                    cur_z -= r_stepdown

            elif effective_core == "CIRCLE" and result.circle:
                cx = result.circle.center_x
                cy = result.circle.center_y
                rad = result.circle.radius
                cur_z = start_z - r_stepdown
                while cur_z >= final_z - 1e-4:
                    cmds.append(Path.Command("G0", {"X": cx, "Y": cy - rad}))
                    cmds.append(Path.Command("G1", {"Z": cur_z, "F": 100.0}))
                    cmds.append(Path.Command("G2", {"X": cx, "Y": cy - rad, "I": 0.0, "J": rad, "F": 250.0}))
                    cur_z -= r_stepdown

            # 2. Residual margin visual path
            for cmd_name, cmd_p in self.residual_commands:
                cmds.append(Path.Command(cmd_name, cmd_p))

            # 3. Perimeter finishing pass at final depth
            if getattr(obj, "EnableFinishing", True) and len(poly) >= 3:
                cmds.append(Path.Command("G0", {"Z": final_z + 2.0}))
                p0 = poly[0]
                cmds.append(Path.Command("G0", {"X": p0[0], "Y": p0[1]}))
                cmds.append(Path.Command("G1", {"Z": final_z, "F": 150.0}))
                for pt in poly[1:]:
                    cmds.append(Path.Command("G1", {"X": pt[0], "Y": pt[1], "F": 400.0}))
                cmds.append(Path.Command("G1", {"X": p0[0], "Y": p0[1], "F": 400.0}))
                cmds.append(Path.Command("G0", {"Z": start_z + 5.0}))

            try:
                obj.Path = Path.Path(cmds)
            except Exception:
                pass

    @classmethod
    def Create(cls, name: str = "OkumaContourPocket", obj: Any = None, parentJob: Any = None) -> Any:
        return Create(name=name, obj=obj, parentJob=parentJob)


def Create(name: str = "OkumaContourPocket", obj: Any = None, parentJob: Any = None) -> Any:
    """Factory function to create a new OkumaContourPocket operation."""
    if obj is None:
        if App and hasattr(App, "ActiveDocument") and App.ActiveDocument:
            doc = App.ActiveDocument
            obj = doc.addObject("Path::FeaturePython", name)
        else:
            # Standalone mock object
            class MockOpObject:
                def __init__(self, obj_name: str) -> None:
                    self.Name = obj_name
                    self.Label = obj_name
                    self.Proxy = None
            obj = MockOpObject(name)

    proxy = ContourPocket(obj)
    if parentJob and hasattr(parentJob, "Operations") and hasattr(parentJob.Operations, "addObject"):
        parentJob.Operations.addObject(obj)
    return obj
