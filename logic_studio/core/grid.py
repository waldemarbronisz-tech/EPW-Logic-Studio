"""The one geometric constant shared between the persistence layer
(core/project.py) and the canvas (ui/canvas/style.py, which re-exports it).
Lives here, not in ui/canvas/style.py, because core/project.py must stay
importable without PySide6 (see tests/test_acceptance.py::
test_headless_engine_no_qt) — the UI layer imports this value, never the
other way around.
"""
GRID_SIZE = 20
