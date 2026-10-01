#!/usr/bin/env python3
"""OkumaCAM Cross-Environment Automated Test Runner.

Executes OkumaCAM unit and integration tests across multiple environments:
1. Native FreeCAD Python (embedded python.exe)
2. Native FreeCADCmd CLI runner (-t TestOkumaCAMApp)
3. Standard Python (system Python, Anaconda, CI runner) with automatic shims
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import unittest

_root_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_dir = os.path.join(_root_dir, "OkumaCAM")
_tests_dir = os.path.join(_pkg_dir, "tests")

# Add roots to sys.path
for d in (_root_dir, _pkg_dir):
    if d not in sys.path:
        sys.path.insert(0, d)


def find_freecad_binaries() -> tuple[str | None, str | None]:
    """Find FreeCAD python.exe and FreeCADCmd.exe if installed on the system."""
    search_dirs = [
        os.environ.get("FREECAD_PATH", ""),
        r"C:\Program Files\FreeCAD 1.1\bin",
        r"C:\Program Files\FreeCAD 1.0\bin",
        r"C:\Program Files (x86)\FreeCAD 1.1\bin",
        r"C:\Program Files (x86)\FreeCAD 1.0\bin",
    ]
    py_exe = None
    cmd_exe = None

    for d in search_dirs:
        if not d or not os.path.isdir(d):
            continue
        candidate_py = os.path.join(d, "python.exe")
        candidate_cmd = os.path.join(d, "freecadcmd.exe")
        if os.path.exists(candidate_cmd) and not cmd_exe:
            cmd_exe = candidate_cmd
        if os.path.exists(candidate_py) and not py_exe:
            py_exe = candidate_py

    return py_exe, cmd_exe


def run_via_freecad_cmd(freecad_cmd: str, verbose: bool = False) -> int:
    """Run tests natively inside FreeCADCmd using registered TestOkumaCAMApp."""
    print(f"--> Running tests via FreeCADCmd: {freecad_cmd}")
    cmd = [freecad_cmd, "-c", "-M", _pkg_dir, "-t", "TestOkumaCAMApp"]
    result = subprocess.run(cmd)
    return result.returncode


def run_via_freecad_python(freecad_py: str, pattern: str = "test_*.py", verbose: bool = True) -> int:
    """Run tests using FreeCAD's embedded python executable."""
    print(f"--> Running tests via FreeCAD Python: {freecad_py}")
    verbosity_flag = "-v" if verbose else ""
    cmd = [
        freecad_py,
        "-m",
        "unittest",
        "discover",
        "-t",
        _pkg_dir,
        "-s",
        _tests_dir,
        "-p",
        pattern,
    ]
    if verbosity_flag:
        cmd.append(verbosity_flag)
    result = subprocess.run(cmd)
    return result.returncode


def run_in_current_process(pattern: str = "test_*.py", verbose: bool = True) -> int:
    """Run test discovery in the active Python process."""
    # Ensure conftest setup is invoked
    try:
        import conftest  # noqa: F401
    except ImportError:
        pass

    print(f"--> Running tests in current Python process ({sys.executable})...")
    loader = unittest.defaultTestLoader
    suite = loader.discover(start_dir=_tests_dir, pattern=pattern, top_level_dir=_pkg_dir)

    runner = unittest.TextTestRunner(verbosity=2 if verbose else 1)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="OkumaCAM Test Suite Runner")
    parser.add_argument(
        "--mode",
        choices=["auto", "current", "freecad-py", "freecad-cmd"],
        default="auto",
        help="Test execution environment (default: auto)",
    )
    parser.add_argument(
        "-p",
        "--pattern",
        default="test_*.py",
        help="Test file pattern to match (default: test_*.py)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Quiet output (reduced verbosity)",
    )

    args = parser.parse_args()
    verbose = not args.quiet

    # If running directly inside FreeCAD's Python
    is_freecad_python = False
    try:
        import FreeCAD  # noqa: F401
        is_freecad_python = True
    except ImportError:
        is_freecad_python = False

    if args.mode == "current" or (args.mode == "auto" and is_freecad_python):
        return run_in_current_process(pattern=args.pattern, verbose=verbose)

    fc_py, fc_cmd = find_freecad_binaries()

    if args.mode == "freecad-cmd":
        if not fc_cmd:
            print("ERROR: FreeCADCmd executable not found. Specify FREECAD_PATH env var.", file=sys.stderr)
            return 1
        return run_via_freecad_cmd(fc_cmd, verbose=verbose)

    if args.mode == "freecad-py":
        if not fc_py:
            print("ERROR: FreeCAD Python executable not found. Specify FREECAD_PATH env var.", file=sys.stderr)
            return 1
        return run_via_freecad_python(fc_py, pattern=args.pattern, verbose=verbose)

    # mode == "auto" (and not is_freecad_python)
    # Prefer FreeCAD Python if installed on machine, otherwise fallback to current process
    if fc_py:
        return run_via_freecad_python(fc_py, pattern=args.pattern, verbose=verbose)
    elif fc_cmd:
        return run_via_freecad_cmd(fc_cmd, verbose=verbose)
    else:
        return run_in_current_process(pattern=args.pattern, verbose=verbose)


if __name__ == "__main__":
    sys.exit(main())
