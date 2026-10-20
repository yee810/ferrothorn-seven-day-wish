"""Run both unittest classes and the project's plain test functions."""
import importlib
import inspect
from pathlib import Path
import unittest

import _bootstrap  # noqa: F401


def suite():
    tests = unittest.TestSuite()
    for path in sorted(Path(__file__).parent.glob("test_*.py")):
        module = importlib.import_module(path.stem)
        tests.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        for name, function in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("test_") and function.__module__ == module.__name__:
                tests.addTest(unittest.FunctionTestCase(function))
    return tests


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(suite())
    raise SystemExit(not result.wasSuccessful())
