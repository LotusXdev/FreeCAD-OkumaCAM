"""Root pytest configuration and FreeCAD environment fixture / mock setup.

Allows pytest to run from any standard Python environment (including Anaconda,
virtual environments, and CI runners) whether or not FreeCAD is installed.
"""

from __future__ import annotations

import os
import sys
from types import ModuleType
from typing import Any, Dict, List, Optional, Sequence, Union

# Ensure OkumaCAM and OkumaCAM/tests are on sys.path
_root_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_dir = os.path.join(_root_dir, "OkumaCAM")
for d in (_root_dir, _pkg_dir):
    if d not in sys.path:
        sys.path.insert(0, d)


# ---------------------------------------------------------------------------
# Attempt to load real FreeCAD if on Python 3.11 and FreeCAD is installed
# ---------------------------------------------------------------------------
_has_real_freecad = False
if "FreeCAD" not in sys.modules:
    # Check known FreeCAD 1.1 / 1.0 installation paths on Windows
    possible_paths = [
        r"C:\Program Files\FreeCAD 1.1\bin",
        r"C:\Program Files\FreeCAD 1.0\bin",
    ]
    if "FREECAD_PATH" in os.environ:
        possible_paths.insert(0, os.environ["FREECAD_PATH"])

    for p in possible_paths:
        if os.path.exists(p) and sys.version_info[:2] == (3, 11):
            if hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(p)
                except Exception:
                    pass
            if p not in sys.path:
                sys.path.insert(0, p)
            try:
                import FreeCAD  # type: ignore # noqa: F401
                _has_real_freecad = True
                break
            except Exception:
                pass


# ---------------------------------------------------------------------------
# If real FreeCAD is not available, install lightweight FreeCAD / Path shims
# ---------------------------------------------------------------------------
if "FreeCAD" not in sys.modules:
    # Build Mock FreeCAD
    mock_freecad = ModuleType("FreeCAD")

    class MockQuantity:
        def __init__(self, val_str: str):
            self.val_str = str(val_str).strip()
            parts = self.val_str.split()
            self.num = float(parts[0]) if parts else 0.0
            self.unit = parts[1] if len(parts) > 1 else ""

        def getValueAs(self, target_unit: str) -> float:
            if "mm/s" in self.unit:
                if target_unit in ("mm/min", "mm/min."):
                    return self.num * 60.0
                elif target_unit in ("in/min", "IPM"):
                    return (self.num * 60.0) / 25.4
            return self.num

    class MockUnits:
        Quantity = MockQuantity

    class MockParamGroup:
        _store: Dict[str, Any] = {}

        def GetBool(self, key: str, default: bool = False) -> bool:
            return bool(self._store.get(key, default))

        def SetBool(self, key: str, val: bool) -> None:
            self._store[key] = bool(val)

        def GetString(self, key: str, default: str = "") -> str:
            return str(self._store.get(key, default))

        def SetString(self, key: str, val: str) -> None:
            self._store[key] = str(val)

        def GetInt(self, key: str, default: int = 0) -> int:
            return int(self._store.get(key, default))

        def SetInt(self, key: str, val: int) -> None:
            self._store[key] = int(val)

        def GetFloat(self, key: str, default: float = 0.0) -> float:
            return float(self._store.get(key, default))

        def SetFloat(self, key: str, val: float) -> None:
            self._store[key] = float(val)

        def HasGroup(self, name: str) -> bool:
            return False

        def RenameGroup(self, old: str, new: str) -> bool:
            return True

        def Parent(self) -> Any:
            return self

    _param_groups: Dict[str, MockParamGroup] = {}

    def mock_param_get(path: str) -> MockParamGroup:
        if path not in _param_groups:
            _param_groups[path] = MockParamGroup()
        return _param_groups[path]

    class MockConsole:
        @staticmethod
        def PrintLog(msg: str) -> None:
            pass

        @staticmethod
        def PrintMessage(msg: str) -> None:
            pass

        @staticmethod
        def PrintWarning(msg: str) -> None:
            pass

        @staticmethod
        def PrintError(msg: str) -> None:
            pass

    class MockBoundBox:
        def __init__(self, xmin=0.0, xmax=100.0, ymin=0.0, ymax=60.0, zmin=-2.5, zmax=0.0):
            self.XMin = xmin
            self.XMax = xmax
            self.YMin = ymin
            self.YMax = ymax
            self.ZMin = zmin
            self.ZMax = zmax
            self.XLength = xmax - xmin
            self.YLength = ymax - ymin
            self.ZLength = zmax - zmin

    class MockShape:
        def __init__(self):
            self.BoundBox = MockBoundBox()

    class MockObject:
        def __init__(self, obj_type: str, name: str):
            self.Type = obj_type
            self.Name = name
            self.Label = name
            self.Path = None
            self.Proxy = None
            self.Shape = MockShape()
            if "Group" in obj_type or "Compound" in obj_type or "Job" in obj_type:
                self.Group: List[Any] = []
            self.ToolController = None

        def addProperty(self, prop_type: str, name: str, group: str = "", doc: str = ""):
            if not hasattr(self, name):
                setattr(self, name, None)


    class MockDocument:
        def __init__(self, name: str):
            self.Name = name
            self.Label = name
            self.Objects: List[MockObject] = []

        def addObject(self, obj_type: str, name: str) -> MockObject:
            obj = MockObject(obj_type, name)
            self.Objects.append(obj)
            return obj

        def recompute(self) -> None:
            pass

        def getObject(self, name: str) -> Optional[MockObject]:
            for obj in self.Objects:
                if obj.Name == name or obj.Label == name:
                    return obj
            return None

    _documents: Dict[str, MockDocument] = {}
    _active_document: Optional[MockDocument] = None

    def mock_new_document(name: str) -> MockDocument:
        doc = MockDocument(name)
        _documents[name] = doc
        mock_freecad.ActiveDocument = doc
        return doc

    def mock_close_document(name: str) -> None:
        if name in _documents:
            del _documents[name]
        mock_freecad.ActiveDocument = next(iter(_documents.values()), None)

    mock_freecad.Units = MockUnits
    mock_freecad.ParamGet = mock_param_get
    mock_freecad.Console = MockConsole
    mock_freecad.newDocument = mock_new_document
    mock_freecad.closeDocument = mock_close_document
    mock_freecad.ActiveDocument = None

    mock_freecad.Version = lambda: ["1", "1", "mock", "2026", "MockFreeCAD"]
    mock_freecad.__unit_test__ = []

    sys.modules["FreeCAD"] = mock_freecad
    sys.modules["App"] = mock_freecad

    # Build Mock Path module
    mock_path = ModuleType("Path")

    class MockCommand:
        def __init__(self, name: str, params: Optional[Dict[str, Any]] = None):
            self.Name = name
            self.Parameters = params or {}

        def __repr__(self) -> str:
            return f"Path.Command('{self.Name}', {self.Parameters})"

    class MockPathClass:
        def __init__(self, commands: Optional[Sequence[MockCommand]] = None):
            self.Commands = list(commands) if commands else []

    mock_path.Command = MockCommand
    mock_path.Path = MockPathClass
    sys.modules["Path"] = mock_path

    # Build Mock PathScripts.PathUtils module
    mock_pathscripts = ModuleType("PathScripts")
    mock_pathutils = ModuleType("PathScripts.PathUtils")

    def mock_get_path_with_placement(obj: Any) -> Any:
        return getattr(obj, "Path", MockPathClass())

    mock_pathutils.getPathWithPlacement = mock_get_path_with_placement
    mock_pathscripts.PathUtils = mock_pathutils
    sys.modules["PathScripts"] = mock_pathscripts
    sys.modules["PathScripts.PathUtils"] = mock_pathutils

    # Build Mock FreeCADGui module
    mock_gui = ModuleType("FreeCADGui")

    class MockWorkbench:
        MenuText = ""
        ToolTip = ""
        Icon = ""

        def appendToolbar(self, name: str, items: Sequence[str]) -> None:
            pass

        def appendMenu(self, name: str, items: Sequence[str]) -> None:
            pass

    mock_gui.Workbench = MockWorkbench
    mock_gui.addCommand = lambda name, cmd: None
    mock_gui.addWorkbench = lambda wb: None
    sys.modules["FreeCADGui"] = mock_gui

