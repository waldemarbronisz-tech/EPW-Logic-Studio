"""The one geometric constant shared between the persistence layer
(core/project.py) and the canvas (ui/canvas/style.py, which re-exports it as
GRID_SNAP — that's the name used everywhere else; this module keeps the
original GRID_SIZE name to avoid an unrelated rename of a headless module).
Lives here, not in ui/canvas/style.py, because core/project.py must stay
importable without PySide6 (see tests/test_acceptance.py::
test_headless_engine_no_qt) — the UI layer imports this value, never the
other way around.

feat/editor-modes-and-geometry §1.1: dropped from 20 to 10 — the value block
origins/ports snap to (block placement) — independent of PORT_PITCH (20, the
spacing between a gate's own inputs, see ui/canvas/style.py). A finer snap
grid gives more placement precision now that gate bodies are a fixed size
rather than growing with input count.
"""
GRID_SIZE = 10
